import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { mountSumoLiveMap } from './sumo-env.js';
import { mountBenchmarkView, setBenchmarkTab } from './benchmark-mount.jsx';
import { mountGauges } from './gauge.js';
import { initModes } from './modes/index.js';

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
    label: '2×2 Grid',
    title: 'East Austin · 2×2',
    menuSub: 'Poquito / Alamo corridor',
    place: 'Poquito & E 14th, Austin',
    zone: 'Poquito corridor',
    queuedRoad: 'Poquito · Eastbound',
    mapCenter: [-97.7219, 30.2673],
    mapZoom: 15.6,
    liveCenter: [-97.7219, 30.2673],
    liveZoom: 15.8,
    // Poquito / Alamo / Coleto with the E 13th–E 14th cross streets.
    route: [
      [-97.7245, 30.2689], [-97.7192, 30.2689],
      [-97.7192, 30.2670], [-97.7245, 30.2670],
      [-97.7245, 30.2649], [-97.7192, 30.2649]
    ],
    crossRoute: [
      [-97.7245, 30.2704], [-97.7245, 30.2649],
      [-97.7192, 30.2704], [-97.7192, 30.2649]
    ]
  },
  'grid-3x3': {
    label: '3×3 Grid',
    title: 'East Austin · 3×3',
    menuSub: 'Chicon / Coleto corridor',
    place: 'Chicon & E 13th, Austin',
    zone: 'Chicon corridor',
    queuedRoad: 'Chicon · Northbound',
    mapCenter: [-97.7219, 30.2675],
    mapZoom: 15.2,
    liveCenter: [-97.7219, 30.2675],
    liveZoom: 15.4,
    // Expanded Chicon / Poquito / Alamo / Coleto corridor.
    route: [
      [-97.7262, 30.2712], [-97.7168, 30.2712],
      [-97.7168, 30.2689], [-97.7262, 30.2689],
      [-97.7262, 30.2670], [-97.7168, 30.2670],
      [-97.7168, 30.2649], [-97.7262, 30.2649]
    ],
    crossRoute: [
      [-97.7262, 30.2712], [-97.7262, 30.2649],
      [-97.7219, 30.2712], [-97.7219, 30.2649],
      [-97.7168, 30.2712], [-97.7168, 30.2649]
    ]
  },
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
    // Monte-Carlo circuit streets.
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
      [7.42931, 43.73916], [7.42912, 43.73896], [7.42896, 43.7388], [7.42884, 43.73877],
      [7.42875, 43.73868], [7.42872, 43.73858], [7.42845, 43.73835]
    ],
    crossRoute: [
      [7.42438, 43.74012], [7.42443, 43.74015], [7.4246, 43.74033], [7.42485, 43.74061],
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
    mapCenter: [10.1815, 36.8065],
    mapZoom: 12.8,
    liveCenter: [10.1815, 36.8065],
    liveZoom: 15.1,
    // Avenue Jean Jaurès corridor, Tunis.
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
  }
};

let activeScenario = 'monaco';
try {
  const savedScenario = localStorage.getItem(SCENARIO_KEY);
  if (savedScenario && SCENARIOS[savedScenario]) activeScenario = savedScenario;
} catch {
  // Keep the default scenario if storage is unavailable.
}

function getScenario() {
  return SCENARIOS[activeScenario] || SCENARIOS.monaco;
}

let map = null;
let benchmarkMounted = false;
let benchmarkTab = 'overview';
let mapFocusMarker = null;

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

/* Every menu offers all four scenarios. The two headless SUMO grids are grouped
   apart because they draw the TraCI network on the canvas scene (and their own 3D
   environment) instead of the Mapbox basemap, so the layer toggles do not apply. */
function renderScenarioMenus() {
  scenarioMenus.forEach((menu) => {
    const places = Object.entries(SCENARIOS).filter(([key]) => !key.startsWith('grid-'));
    const grids = Object.entries(SCENARIOS).filter(([key]) => key.startsWith('grid-'));
    menu.innerHTML = `
      <div class="scenario-menu-head" role="presentation">
        <span>Simulation scenario</span>
      <small>${places.length + grids.length} available</small>
      </div>
      ${places.map(([key, scenario]) => scenarioOptionMarkup(key, scenario)).join('')}
      ${
        grids.length
          ? `<div class="scenario-menu-group" role="presentation"><span>SUMO grids</span><small>Live TraCI</small></div>
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

/* The grid scenarios render their own 3D environment, so the Mapbox-only
   layer toggles have nothing to act on there. */
function syncLayerMenuAvailability() {
  const grid = ['grid-2x2', 'grid-3x3'].includes(activeScenario);
  document.querySelectorAll('[data-map-layer]').forEach((option) => {
    const layer = option.dataset.mapLayer;
    if (layer === 'basemap') {
      option.disabled = grid;
      option.classList.toggle('is-disabled', grid);
      option.setAttribute('aria-disabled', String(grid));
      option.title = grid ? 'Automatically disabled — the 3D grid uses its own environment' : '';
      // When switching to a grid scenario, force-hide the basemap layer
      if (grid) {
        option.setAttribute('aria-checked', 'false');
        option.classList.remove('is-selected');
        setMapLayerVisibility('basemap', false);
      }
    }
  });
}

function applyScenarioChrome() {
  const scenario = getScenario();
  syncLayerMenuAvailability();
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
    const gridLabel = activeScenario === 'grid-3x3' ? '3×3' : '2×2';
    simStart.innerHTML = `<svg class="ico"><use href="#i-refresh"/></svg>Start ${gridLabel}`;
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
function retargetSimulation(name) {
  const grid = ['grid-2x2', 'grid-3x3'].includes(name) ? name : null;
  const live = latestSimulationState;
  if (!grid || !live) return;
  if (!['running', 'paused', 'starting'].includes(live.status)) return;
  if (live.scenario === grid) return;
  simulationFetch('/api/simulation/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario: grid, speed: simulationSpeed })
  })
    .then((response) => (response.ok ? response.json() : null))
    .then((state) => state && updateSimulationState(state))
    .catch(() => {});
}

function setScenario(name, { announce = true } = {}) {
  if (!SCENARIOS[name]) return;
  activeScenario = name;
  try {
    localStorage.setItem(SCENARIO_KEY, activeScenario);
  } catch {
    // Scenario still applies for the current session.
  }
  applyScenarioChrome();
  loadLiveWeather();
  renderPolicyControl();
  if (activeGridNetwork()) loadPolicy();

  const scenario = getScenario();
  if (map) {
    map.flyTo({ center: scenario.mapCenter, zoom: scenario.mapZoom, duration: 1000, essential: true });
    mapFocusMarker?.setLngLat(scenario.mapCenter);
  }
  refreshLiveMapScenario();
  loadSimulationNetwork(activeScenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2');
  retargetSimulation(activeScenario);

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
  activeLiveTab = ['events', 'optimize', 'predict', 'roam'].includes(tabName) ? tabName : 'events';
  setActiveNav('Live Map');
  setActiveViewTab('Dashboard');
  if (liveMapView?.hidden) showView('Live Map');
  setLiveSubnavActive(activeLiveTab);
  liveMapView?.classList.toggle('live-roam-mode', activeLiveTab === 'roam');
  if (activeLiveTab === 'roam') {
    if (roamRestoreCollapsed === null) {
      roamRestoreCollapsed = liveMapView?.classList.contains('live-panels-collapsed') ? 1 : 0;
    }
    liveMapView?.classList.add('live-panels-collapsed');
  } else if (roamRestoreCollapsed !== null) {
    liveMapView?.classList.toggle('live-panels-collapsed', roamRestoreCollapsed === 1);
    roamRestoreCollapsed = null;
  }

  const url = new URL(window.location.href);
  url.searchParams.set('view', 'live-map');
  if (activeLiveTab) url.searchParams.set('tab', activeLiveTab);
  else url.searchParams.delete('tab');
  window.history.replaceState(null, '', url);

  document.dispatchEvent(new CustomEvent('sumo:livetabchange', { detail: { tab: activeLiveTab } }));
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

function ensureLiveMap() {
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
  benchmarkTab = tab.dataset.benchmarkTab || 'overview';
  setBenchmarkTab(benchmarkTab);
}));

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
  item.addEventListener('click', () => {
    const name = item.dataset.nav;
    setActiveNav(name);
    setActiveViewTab(name === 'Settings' ? 'Settings' : 'Dashboard');
    showView(name);
  });
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
  link.addEventListener('click', () => {
    setActiveNav('Roles & Permissions');
    setActiveViewTab('Dashboard');
    showView('Roles & Permissions');
    setAccessTab(link.dataset.accessLink);
  });
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
  link.addEventListener('click', () => {
    setActiveNav('Benchmark'); setActiveViewTab('Dashboard'); showView('Benchmark');
    benchmarkTab = link.dataset.benchmarkTab || 'overview';
    setBenchmarkTab(benchmarkTab);
    document.querySelectorAll('#benchmarkSubnav [data-benchmark-tab]').forEach((item) => {
      item.classList.toggle('is-active', item === link);
    });
  });
});

liveLinks.forEach((link) => {
  link.addEventListener('click', () => selectLiveTab(link.dataset.liveTab || ''));
});

liveModeTabs.forEach((tab) => {
  tab.addEventListener('click', () => selectLiveTab(tab.dataset.liveMode || ''));
});

document.querySelectorAll('.view-tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    const name = tab.dataset.view || 'Dashboard';
    setActiveViewTab(name);
    setActiveNav(name === 'Settings' ? 'Settings' : 'Dashboard');
    showView(name);
  });
});

function exitLiveMap() {
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  setActiveNav('Dashboard');
  setActiveViewTab('Dashboard');
  showView('Dashboard');

  const url = new URL(window.location.href);
  if (url.searchParams.get('view') === 'live-map') {
    url.searchParams.delete('view');
    url.searchParams.delete('tab');
    window.history.replaceState(null, '', url);
  }
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
let sumo3d = null;
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
const SIMULATION_DAY_PROFILE = [
  14, 10, 8, 9, 18, 34, 58, 82, 96, 72, 54, 49,
  52, 50, 47, 55, 74, 92, 100, 84, 62, 46, 32, 21
];

function buildSimulationProfile() {
  if (!simulationProfile || simulationProfile.childElementCount) return;
  SIMULATION_DAY_PROFILE.forEach((height) => {
    const bar = document.createElement('i');
    bar.style.setProperty('--h', `${height}%`);
    simulationProfile.append(bar);
  });
}

function formatSimulationTime(seconds) {
  const value = Math.max(0, Math.min(86400, Number(seconds) || 0));
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
let latestSimulationState = null;
let simulationSeeded = false;
let policyCatalog = [];
let activePolicyMethod = 'mp';
const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;
const SIMULATION_BOUNDS = {
  'grid-2x2': { west: -97.7245, east: -97.7192, south: 30.2649, north: 30.2704, width: 400, height: 400 },
  'grid-3x3': { west: -97.7262, east: -97.7168, south: 30.2649, north: 30.2712, width: 600, height: 600 }
};

function simulationFetch(path, options) {
  return fetch(`${API_BASE}${path}`, options);
}

const POLICY_GRID = { 'grid-2x2': 'grid2x2', 'grid-3x3': 'grid3x3' };

function activeGridNetwork() {
  return POLICY_GRID[activeScenario] || null;
}

function policyLabel(method) {
  return policyCatalog.find((entry) => entry.method === method)?.label || method;
}

function renderPolicyControl() {
  const select = document.getElementById('liveControllerSelect');
  if (!select) return;
  const network = activeGridNetwork();
  select.closest('.live-controller')?.classList.toggle('is-disabled', !network);
  select.disabled = !network;
  if (!policyCatalog.length) return;
  select.innerHTML = policyCatalog
    .map((entry) => `<option value="${entry.method}">${entry.label}</option>`)
    .join('');
  select.value = activePolicyMethod;
}

async function loadPolicy() {
  try {
    const response = await simulationFetch('/api/policy');
    if (!response.ok) return;
    const body = await response.json();
    policyCatalog = Array.isArray(body.catalog) ? body.catalog : [];
    activePolicyMethod = body.method || activePolicyMethod;
    renderPolicyControl();
  } catch {
    renderPolicyControl();
  }
}

async function selectPolicy(method) {
  const network = activeGridNetwork();
  if (!network) return;
  try {
    const response = await simulationFetch('/api/policy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method, network })
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.detail || `controller ${response.status}`);
    policyCatalog = Array.isArray(body.catalog) ? body.catalog : policyCatalog;
    activePolicyMethod = body.method || method;
    renderPolicyControl();
    showToast(`Controller: ${policyLabel(activePolicyMethod)} (next run).`, {
      duration: activePolicyMethod === 'llm_team' ? 5200 : 2200
    });
    if (activePolicyMethod === 'llm_team') {
      showToast('LLM team uses OpenCode Go and makes paid calls.', { duration: 5200 });
    }
  } catch (error) {
    renderPolicyControl();
    showToast(error instanceof Error ? error.message : 'Controller unavailable.');
  }
}

document.getElementById('liveControllerSelect')?.addEventListener('change', (event) => {
  selectPolicy(event.currentTarget.value);
});

loadPolicy();

function simulationPoint(scenario, x, y) {
  const bounds = SIMULATION_BOUNDS[scenario] || SIMULATION_BOUNDS['grid-2x2'];
  return [
    bounds.west + (Number(x) / bounds.width) * (bounds.east - bounds.west),
    bounds.south + (Number(y) / bounds.height) * (bounds.north - bounds.south)
  ];
}

function refreshSimulationVehicles(state) {
  if (!liveMap || !state?.scenario) return;
  const source = liveMap.getSource('live-vehicles');
  if (!source) return;
  source.setData({
    type: 'FeatureCollection',
    features: (state.vehicles || []).map((vehicle) => ({
      type: 'Feature',
      properties: { waiting: Boolean(vehicle.waiting), speed: Number(vehicle.speed || 0), id: vehicle.id },
      geometry: { type: 'Point', coordinates: Number.isFinite(Number(vehicle.lng)) && Number.isFinite(Number(vehicle.lat)) ? [Number(vehicle.lng), Number(vehicle.lat)] : simulationPoint(state.scenario, vehicle.x, vehicle.y) }
    }))
  });
}

function updateSimulationState(state) {
  if (!state) return;
  latestSimulationState = state;
  if (sumo3d) sumo3d.update({ ...state, scenario: activeScenario });
  if (simulationClock) simulationClock.textContent = state.clock || '00:00:00';
  setSimulationStatus(state.status);
  if (simulationMetrics) simulationMetrics.textContent = `${state.metrics?.vehicles || 0} vehicles`;
  if (simulationTime && Number.isFinite(Number(state.simulationTime))) simulationTime.value = state.simulationTime;
  paintSimulationTimeline(simulationTime?.value || 0);
  refreshSimulationVehicles(state);
}

function formatSimulationClock(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  return `${String(Math.floor(value / 3600)).padStart(2, '0')}:${String(Math.floor(value % 3600 / 60)).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
}

simulationTime?.addEventListener('input', () => {
  const seconds = Number(simulationTime.value);
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
    const scenario = activeScenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2';
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

/* The 3D scene's own SUMO strip: start / pause / single-step / speed. */
async function handleSumoSceneAction(action, extra = {}) {
  const scenario = activeScenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2';
  const status = simulationStatus?.dataset.state;
  const post = async (path, body) => {
    connectSimulationSocket();
    try {
      const response = await simulationFetch(
        path,
        body
          ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
          : { method: 'POST' }
      );
      if (!response.ok) throw new Error(`simulation ${response.status}`);
      updateSimulationState(await response.json());
    } catch {
      showToast('Simulation service is offline.');
    }
  };

  if (action === 'start') return post('/api/simulation/start', { scenario, speed: simulationSpeed });
  if (action === 'pause') {
    return post(status === 'paused' ? '/api/simulation/resume' : '/api/simulation/pause');
  }
  if (action === 'step') return post('/api/simulation/step', { scenario, count: 1 });
  if (action === 'speed') {
    simulationSpeed = Number(extra.speed) || 1;
    const chip = document.getElementById('simulationSpeed');
    if (chip) chip.textContent = `${simulationSpeed}×`;
    return post('/api/simulation/speed', { scenario, speed: simulationSpeed });
  }
  return undefined;
}

function connectSimulationSocket() {
  if (simulationSocket || !window.WebSocket) return;
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  simulationSocket = new WebSocket(`${protocol}://${window.location.hostname}:8000/ws/simulation`);
  simulationSocket.onmessage = (event) => updateSimulationState(JSON.parse(event.data));
  simulationSocket.onclose = () => { simulationSocket = null; };
}

document.getElementById('simulationStart')?.addEventListener('click', async () => {
  connectSimulationSocket();
  const scenario = activeScenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2';
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
document.getElementById('simulationSpeed')?.addEventListener('click', async (event) => {
  simulationSpeed = simulationSpeed === 1 ? 5 : simulationSpeed === 5 ? 20 : 1;
  event.currentTarget.textContent = `${simulationSpeed}×`;
  try {
    const response = await simulationFetch('/api/simulation/speed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario: activeScenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2', speed: simulationSpeed }) });
    updateSimulationState(await response.json());
  } catch {
    showToast('Simulation service is offline.');
  }
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
  if (['grid-2x2', 'grid-3x3'].includes(activeScenario)) {
    initLiveMap();
    return;
  }
  if (!liveMap) {
    initLiveMap();
    return;
  }
  const container = $('liveMap');
  const sumoScene = $('sumo3dScene');
  if (container) { container.hidden = false; container.style.display = ''; }
  if (sumoScene) { sumoScene.hidden = true; sumoScene.style.display = 'none'; }
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
    liveMap.setFog({
      color: '#eef0eb',
      'high-color': '#e5e9e2',
      'horizon-blend': 0.22,
      'space-color': '#f5f6f2',
      'star-intensity': 0
    });
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

  if (!liveMap.getSource('live-sumo-road')) {
    liveMap.addSource('live-sumo-road', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!liveMap.getLayer('live-mapbox-layout')) {
    liveMap.addLayer({
      id: 'live-mapbox-layout', type: 'line', source: 'live-route',
      layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'visible' },
      paint: { 'line-color': '#6f91a4', 'line-width': 5, 'line-opacity': 0.34 }
    });
  }
  if (!liveMap.getLayer('live-sumo-road')) {
    liveMap.addLayer({
      id: 'live-sumo-road', type: 'line', source: 'live-sumo-road',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#5f9c2b', 'line-width': 3.2, 'line-opacity': 0.92 }
    });
  }
  if (!liveMap.getSource('live-vehicles')) {
    liveMap.addSource('live-vehicles', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!liveMap.getLayer('live-vehicles')) {
    liveMap.addLayer({
      id: 'live-vehicles', type: 'circle', source: 'live-vehicles',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 14, 3.5, 17, 6],
        'circle-color': ['case', ['get', 'waiting'], '#e66b52', '#3b9d7d'],
        'circle-stroke-color': '#fffdf5', 'circle-stroke-width': 1.4,
        'circle-opacity': 0.96
      }
    });
  }
  if (liveMap.getLayer('live-sumo-road')) liveMap.setLayoutProperty('live-sumo-road', 'visibility', 'visible');
  loadSimulationNetwork(activeScenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2');
  refreshSimulationVehicles(latestSimulationState);

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

  ['live-fog', 'live-route-glow', 'live-cross-route', 'live-route-casing', 'live-route'].forEach((layerId) => {
    if (liveMap.getLayer(layerId)) {
      liveMap.setLayoutProperty(
        layerId,
        'visibility',
        (layerId === 'live-fog' ? LIVE_FOG_ENABLED : LIVE_ROUTE_OVERLAYS_ENABLED) ? 'visible' : 'none'
      );
    }
  });

  clearLiveMapSceneMarkers();
  addLiveSceneMarkers(scene);
}

async function loadSimulationNetwork(scenario) {
  if (!liveMap) return;
  try {
    const response = await simulationFetch(`/api/simulation/network/${scenario}`);
    if (!response.ok) return;
    const data = await response.json();
    liveMap.getSource('live-sumo-road')?.setData(data);
  } catch {
    // The map remains usable when the SUMO service is offline.
  }
}

function initLiveMap() {
  const container = $('liveMap');
  if (!container) return;
  const sumoScene = $('sumo3dScene');
  if (['grid-2x2', 'grid-3x3'].includes(activeScenario)) {
    container.closest('.live-map-view')?.classList.add('is-sumo-3d');
    container.hidden = true;
    container.style.display = 'none';
    if (liveMap) liveMap.getContainer().style.display = 'none';
    const vignette = document.querySelector('.live-map-vignette');
    if (vignette) vignette.style.display = 'none';
    if (sumoScene) {
      sumoScene.hidden = false;
      sumoScene.style.display = 'block';
      sumoScene.classList.add('is-grid-mode');
      const gridState = { ...(latestSimulationState || {}), scenario: activeScenario, vehicles: latestSimulationState?.vehicles || [] };
      /* A run may already be live, so pick up the stream and one snapshot
         instead of waiting for the operator to press Start again. */
      connectSimulationSocket();
      if (!simulationSeeded) {
        simulationSeeded = true;
        simulationFetch('/api/simulation/state')
          .then((response) => (response.ok ? response.json() : null))
          .then((sim) => sim && updateSimulationState(sim))
          .catch(() => { simulationSeeded = false; });
      }
      if (sumo3d?.scenario && sumo3d.scenario !== activeScenario) { sumo3d.destroy?.(); sumo3d = null; }
      sumo3d ||= mountSumoLiveMap(sumoScene, gridState, { onSimAction: handleSumoSceneAction });
      sumo3d.update(gridState);
      window.requestAnimationFrame(() => sumo3d?.update({ ...gridState, scenario: activeScenario }));
    }
    return;
  }
  container.closest('.live-map-view')?.classList.remove('is-sumo-3d');
  container.hidden = false;
  container.style.display = '';
  if (liveMap) liveMap.getContainer().style.display = '';
  const vignette = document.querySelector('.live-map-vignette');
  if (vignette) vignette.style.display = '';
  if (sumoScene) { sumoScene.hidden = true; sumoScene.style.display = 'none'; sumoScene.classList.remove('is-grid-mode'); }
  /* Leaving a grid tears the WebGL scene down instead of keeping it mounted
     off-screen, so its render loop and the map tools stay with the map. */
  if (sumo3d) { sumo3d.destroy?.(); sumo3d = null; }
  if (liveMap) {
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
    config: { basemap: { lightPreset: MAP_STYLES[activeMapStyle].preset } },
    maxPitch: 72
  });

  // The modes layer falls back to this global when no getter is injected.
  window.sumoLiveMap = liveMap;

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
  if (!style || !liveMap || styleName === activeMapStyle) return;
  activeMapStyle = styleName;
  liveMap.setConfigProperty('basemap', 'lightPreset', style.preset);
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
    /* In a SUMO grid the same buttons drive the 3D environment's camera. */
    if (sumo3d && ['grid-2x2', 'grid-3x3'].includes(activeScenario)) {
      if (action === 'zoom-in') sumo3d.zoomIn();
      if (action === 'zoom-out') sumo3d.zoomOut();
      if (action === 'reset') sumo3d.reset();
      return;
    }
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
  showToast: (message, options) => showToast(message, options)
});

const LIVE_ACTION_MESSAGES = {
  accelerate: 'Acceleration plan applied to the active corridor.',
  reroute: 'Reroute advisory published to connected vehicles.',
  restrict: 'Lane restriction staged for operator approval.',
  deviation: 'Deviation monitoring enabled for this sector.',
  monitor: 'Live monitoring focused on the active sector.',
  deactivate: 'Adaptive control actions paused.'
};

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

    if (button.classList.contains('live-action')) {
      document.querySelectorAll('.live-action').forEach((tile) => tile.classList.remove('is-active'));
      if (action !== 'deactivate') button.classList.add('is-active');
      showToast(LIVE_ACTION_MESSAGES[action] || 'Corridor action applied.');
    }
  });
});

document.querySelectorAll('[data-map-style]').forEach((option) => {
  option.addEventListener('click', () => {
    applyLiveMapStyle(option.dataset.mapStyle);
    option.closest('.live-style-menu')?.setAttribute('hidden', '');
    option.closest('.live-style-picker')?.querySelector('[data-live-action="style"]')?.setAttribute('aria-expanded', 'false');
  });
});

function setMapLayerVisibility(layerName, enabled) {
  if (!liveMap) return;
  if (layerName === 'basemap') {
    liveMap.getStyle().layers.forEach((layer) => {
      if (!layer.id.startsWith('live-')) liveMap.setLayoutProperty(layer.id, 'visibility', enabled ? 'visible' : 'none');
    });
  }
  if (layerName === 'sumo-road') {
    ['live-sumo-road', 'live-route-glow', 'live-cross-route', 'live-route-casing', 'live-route'].forEach((id) => {
      if (liveMap.getLayer(id)) liveMap.setLayoutProperty(id, 'visibility', enabled ? 'visible' : 'none');
    });
  }
  if (layerName === 'vehicles') {
    // Toggle vehicle / model layers produced by the SUMO live feed
    ['live-vehicles', 'live-vehicle-labels', 'live-vehicle-models'].forEach((id) => {
      if (liveMap.getLayer(id)) liveMap.setLayoutProperty(id, 'visibility', enabled ? 'visible' : 'none');
    });
  }
}

document.querySelectorAll('[data-map-layer]').forEach((option) => {
  option.addEventListener('click', () => {
    if (option.disabled) return;
    const enabled = option.getAttribute('aria-checked') !== 'true';
    option.setAttribute('aria-checked', String(enabled));
    option.classList.toggle('is-selected', enabled);
    setMapLayerVisibility(option.dataset.mapLayer, enabled);
    if (option.dataset.mapLayer === 'basemap') setPanelTheme(enabled);
  });
});

document.querySelectorAll('[data-live-panels-toggle]').forEach((toggle) => toggle.addEventListener('click', (event) => {
  const collapsed = liveMapView?.classList.toggle('live-panels-collapsed');
  event.currentTarget.setAttribute('aria-label', collapsed ? 'Expand panels' : 'Collapse panels');
  event.currentTarget.setAttribute('title', collapsed ? 'Expand panels' : 'Collapse panels');
  event.currentTarget.textContent = collapsed ? 'Panels' : 'Panels';
}));
document.getElementById('simulationResetView')?.addEventListener('click', () => sumo3d?.reset());

function setPanelTheme(light) {
  const enabled = liveMapView ? liveMapView.classList.toggle('live-panels-light', Boolean(light)) : Boolean(light);
  document.querySelectorAll('[data-panel-theme-toggle]').forEach((button) => {
    button.classList.toggle('is-light', enabled);
    button.setAttribute('title', enabled ? 'Panels: Light' : 'Panels: Dark');
    button.setAttribute('aria-label', enabled ? 'Switch panels to dark mode' : 'Switch panels to light mode');
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
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set('view', 'access');
    url.searchParams.set('tab', tabName);
    window.history.replaceState(null, '', url);
  }
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

document.querySelectorAll('[data-settings-tab]').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('[data-settings-tab]').forEach((node) => {
      const active = node === tab;
      node.classList.toggle('is-active', active);
      node.setAttribute('aria-selected', String(active));
    });
    document.querySelectorAll('[data-settings-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.settingsPanel !== tab.dataset.settingsTab;
    });
    settingsView?.scrollTo({ top: 0, behavior: 'smooth' });
  });
});

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

document.querySelectorAll('[data-integration-connect]').forEach((button) => {
  button.addEventListener('click', () => {
    const next = button.getAttribute('aria-pressed') !== 'true';
    button.setAttribute('aria-pressed', String(next));
    button.querySelector('use')?.setAttribute('href', next ? '#i-check' : '#i-link');
    const label = button.querySelector('span');
    if (label) label.textContent = next ? 'Connected' : 'Connect';
    button.closest('.integration-card')?.classList.toggle('is-connected', next);
    showToast(`${button.dataset.label || 'Integration'} ${next ? 'connected' : 'disconnected'}.`);
  });
});
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
