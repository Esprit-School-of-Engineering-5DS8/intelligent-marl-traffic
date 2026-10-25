/**
 * Gauge — reusable semicircular gauge rendered as inline SVG.
 *
 * Usage (vanilla):
 *   const gauge = Gauge({ value: 52, min: 0, max: 100, labels: [0, 50, 100] });
 *   host.append(gauge.el);
 *   gauge.setValue(61);
 *
 * Declarative:
 *   <div data-gauge data-value="52" data-min="0" data-max="100"
 *        data-labels="0,50,100" data-ticks="49" data-name="Traffic Load"></div>
 *   mountGauges();
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

/* Cropped dial geometry.
 *
 * The dial is a 200deg arc whose centre sits near the bottom of the viewBox,
 * so the card only shows the top slice of a larger speedometer: the scale
 * enters at the lower-left, sweeps over the top and leaves at the lower-right.
 * Every point that falls outside the viewBox is clipped by the SVG itself,
 * which keeps the crop identical at any rendered width.
 */
const VIEW_W = 200;
const VIEW_H = 96;
const CX = 100;
const CY = 84;
const RADIUS = 72;
const START_DEG = 190;
const END_DEG = -10;
const SWEEP_DEG = START_DEG - END_DEG;

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

function polar(radius, degrees) {
  const radians = (degrees * Math.PI) / 180;
  return {
    x: CX + radius * Math.cos(radians),
    y: CY - radius * Math.sin(radians)
  };
}

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

export function Gauge({
  value = 0,
  min = 0,
  max = 100,
  ticks = 49,
  labels = [0, 50, 100],
  label,
  name = label || 'Value',
  unit = '%'
} = {}) {
  const safeMax = max === min ? min + 1 : max;
  const fraction = (input) => (clamp(Number(input), min, safeMax) - min) / (safeMax - min);
  const angleFor = (input) => START_DEG - fraction(input) * SWEEP_DEG;
  const arcLength = (RADIUS * SWEEP_DEG * Math.PI) / 180;

  let currentValue = clamp(Number(value), min, safeMax);

  const el = document.createElement('div');
  el.className = 'gauge';
  el.setAttribute('role', 'img');

  const svg = svgEl('svg', {
    viewBox: `0 0 ${VIEW_W} ${VIEW_H}`,
    class: 'gauge-svg',
    'aria-hidden': 'true',
    focusable: 'false'
  });

  const start = polar(RADIUS, START_DEG);
  const end = polar(RADIUS, END_DEG);
  const arcPath = `M ${start.x} ${start.y} A ${RADIUS} ${RADIUS} 0 1 1 ${end.x} ${end.y}`;

  // Thin light-gray base arc.
  svg.append(svgEl('path', {
    d: arcPath,
    class: 'gauge-base',
    'vector-effect': 'non-scaling-stroke'
  }));

  // Fine tick ring outside the arc.
  const tickGroup = svgEl('g', { class: 'gauge-ticks' });
  const tickNodes = [];
  const tickCount = Math.max(8, ticks);
  for (let index = 0; index < tickCount; index += 1) {
    const ratio = index / (tickCount - 1);
    const angle = START_DEG - ratio * SWEEP_DEG;
    const isMajor = index % 5 === 0;
    const inner = polar(RADIUS + 3, angle);
    const outer = polar(isMajor ? RADIUS + 9.5 : RADIUS + 6.5, angle);
    const tick = svgEl('line', {
      x1: inner.x,
      y1: inner.y,
      x2: outer.x,
      y2: outer.y,
      class: `gauge-tick${isMajor ? ' is-major' : ''}`,
      'vector-effect': 'non-scaling-stroke'
    });
    tick.dataset.ratio = String(ratio);
    tickNodes.push(tick);
    tickGroup.append(tick);
  }
  svg.append(tickGroup);

  // Orange progress arc.
  const progress = svgEl('path', {
    d: arcPath,
    class: 'gauge-progress',
    'vector-effect': 'non-scaling-stroke'
  });
  progress.style.strokeDasharray = `${arcLength}`;
  progress.style.strokeDashoffset = `${arcLength}`;
  svg.append(progress);

  // Ghost arc: a faint reference value (the live reading) kept under the
  // projected one when a mode previews forecast gauges.
  const ghost = svgEl('path', {
    d: arcPath,
    class: 'gauge-ghost',
    'vector-effect': 'non-scaling-stroke'
  });
  ghost.style.strokeDasharray = `${arcLength}`;
  ghost.style.strokeDashoffset = `${arcLength}`;
  svg.append(ghost);

  // Marker: a dot parked at the top of the dial, rotated into place so the
  // needle and the progress arc animate together.
  const marker = svgEl('g', { class: 'gauge-marker' });
  marker.append(svgEl('circle', { cx: CX, cy: CY - RADIUS, r: 4.2 }));
  marker.style.transform = `rotate(${90 - angleFor(min)}deg)`;
  marker.style.transformOrigin = `${CX}px ${CY}px`;
  svg.append(marker);

  // Tiny scale labels under the arc.
  const labelNodes = [];
  const labelGroup = svgEl('g', { class: 'gauge-labels' });
  (labels || []).forEach((labelValue) => {
    const point = polar(RADIUS - 24, angleFor(labelValue));
    const text = svgEl('text', {
      x: Math.min(VIEW_W - 8, Math.max(8, point.x)),
      // Keep the scale labels above the crop line where the dial meets the
      // card's bottom edge.
      y: Math.min(VIEW_H - 11, point.y + 3),
      'text-anchor': 'middle',
      class: 'gauge-label'
    });
    text.textContent = `${labelValue}${unit}`;
    labelGroup.append(text);
    labelNodes.push(text);
  });
  svg.append(labelGroup);

  el.append(svg);

  const prefersReducedMotion = () =>
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

  function paint(input) {
    const ratio = fraction(input);
    progress.style.strokeDashoffset = `${arcLength * (1 - ratio)}`;
    marker.style.transform = `rotate(${90 - angleFor(input)}deg)`;
    tickNodes.forEach((tick) => {
      tick.classList.toggle('is-filled', Number(tick.dataset.ratio) <= ratio + 0.0001);
    });
    el.setAttribute('aria-label', `${name} ${Math.round(input)}${unit}`);
  }

  function setValue(next, { animate = true } = {}) {
    const nextValue = clamp(Number(next), min, safeMax);
    currentValue = nextValue;
    if (!animate || prefersReducedMotion()) {
      progress.style.transition = 'none';
      marker.style.transition = 'none';
      paint(nextValue);
      // Restore transitions on the next frame so later updates animate again.
      requestAnimationFrame(() => {
        progress.style.transition = '';
        marker.style.transition = '';
      });
      return;
    }
    paint(nextValue);
  }

  // First paint: sweep in from zero. The timeout is a safety net for
  // background/occluded tabs where requestAnimationFrame is throttled.
  let painted = false;
  const firstPaint = () => {
    if (painted) return;
    painted = true;
    setValue(value);
  };
  requestAnimationFrame(firstPaint);
  window.setTimeout(firstPaint, 240);

  function setGhost(next) {
    if (next === null || next === undefined || !Number.isFinite(Number(next))) {
      ghost.classList.remove('is-visible');
      return;
    }
    ghost.style.strokeDashoffset = `${arcLength * (1 - fraction(Number(next)))}`;
    ghost.classList.add('is-visible');
  }

  return { el, setValue, setGhost, value: () => currentValue };
}

export function mountGauges(root = document) {
  root.querySelectorAll('[data-gauge]').forEach((host) => {
    if (host.dataset.gaugeReady === 'true') return;
    const gauge = Gauge({
      value: Number(host.dataset.value || 0),
      min: Number(host.dataset.min || 0),
      max: Number(host.dataset.max || 100),
      ticks: Number(host.dataset.ticks || 49),
      labels: (host.dataset.labels || '0,50,100')
        .split(',')
        .map((entry) => Number(entry.trim()))
        .filter((entry) => Number.isFinite(entry)),
      name: host.dataset.name || host.dataset.label || 'Value',
      unit: host.dataset.unit || '%'
    });
    host.append(gauge.el);
    host.gauge = gauge;
    host.dataset.gaugeReady = 'true';
  });
}
