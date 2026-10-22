function mountSumoCanvas(container, initial) {
  const canvas = document.createElement('canvas');
  canvas.className = 'sumo-3d-canvas';
  container.replaceChildren(canvas);
  const ctx = canvas.getContext('2d');
  let state = initial || {}, network = null, frame = 0;
  const resize = () => { const ratio = window.devicePixelRatio || 1; const w = container.clientWidth || 900; const h = container.clientHeight || 600; canvas.width = w * ratio; canvas.height = h * ratio; canvas.style.width = `${w}px`; canvas.style.height = `${h}px`; ctx.setTransform(ratio, 0, 0, ratio, 0, 0); };
  const load = async () => { try { const scenario = state.scenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2'; const apiBase = `${window.location.protocol}//${window.location.hostname}:8000`; const response = await fetch(`${apiBase}/api/simulation/network/${scenario}`); network = response.ok ? await response.json() : null; } catch { network = null; } };
  const draw = () => {
    const w = canvas.clientWidth || container.clientWidth, h = canvas.clientHeight || container.clientHeight;
    ctx.clearRect(0, 0, w, h); ctx.fillStyle = '#0b1218'; ctx.fillRect(0, 0, w, h);
    if (network?.features?.length) {
      const coords = network.features.flatMap((f) => f.geometry.coordinates), lngs = coords.map((p) => p[0]), lats = coords.map((p) => p[1]);
      const west = Math.min(...lngs), east = Math.max(...lngs), south = Math.min(...lats), north = Math.max(...lats), pad = 48;
      const scale = Math.min((w - pad * 2) / Math.max(east - west, 1e-8), (h - pad * 2) / Math.max(north - south, 1e-8));
      const point = ([lng, lat]) => [pad + (lng - west) * scale + (w - pad * 2 - (east - west) * scale) / 2, h - pad - (lat - south) * scale - (h - pad * 2 - (north - south) * scale) / 2];
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      network.features.forEach((feature) => { const line = feature.geometry.coordinates.map(point); ctx.strokeStyle = '#536270'; ctx.lineWidth = 7; ctx.beginPath(); line.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p)); ctx.stroke(); ctx.strokeStyle = '#d9b94d'; ctx.lineWidth = 1.2; ctx.beginPath(); line.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p)); ctx.stroke(); });
      const phase = Math.floor(Number(state.simulationTime || 0) / 8) % 3;
      network.features.forEach((feature, index) => { const coords = feature.geometry.coordinates; if (coords.length < 2) return; const end = point(coords[coords.length - 1]), before = point(coords[coords.length - 2]); const dx = before[0] - end[0], dy = before[1] - end[1], length = Math.max(1, Math.hypot(dx, dy)); const x = end[0] + dx / length * 10, y = end[1] + dy / length * 10; ctx.fillStyle = phase === index % 3 ? '#37d18b' : phase === 1 ? '#f0c84f' : '#ef665c'; ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill(); });
      (state.vehicles || []).forEach((vehicle) => { if (!Number.isFinite(vehicle.lng) || !Number.isFinite(vehicle.lat)) return; const [x, y] = point([vehicle.lng, vehicle.lat]); ctx.save(); ctx.translate(x, y); ctx.rotate((Number(vehicle.angle || 0) * Math.PI) / 180); ctx.fillStyle = vehicle.waiting ? '#ef7060' : '#36c98a'; ctx.fillRect(-7, -3, 14, 6); ctx.restore(); });
    } else { ctx.fillStyle = '#f0c84f'; ctx.font = '14px sans-serif'; ctx.fillText('Loading SUMO network…', 28, 38); }
    frame = requestAnimationFrame(draw);
  };
  resize(); window.addEventListener('resize', resize); load(); draw();
  return { scenario: initial?.scenario === 'grid-3x3' ? 'grid-3x3' : 'grid-2x2', update(next) { const changed = next?.scenario !== state?.scenario; state = next || state; if (changed) load(); }, reset() {}, destroy() { cancelAnimationFrame(frame); window.removeEventListener('resize', resize); container.replaceChildren(); } };
}

export function mountSumoLiveMap(container, state) { return mountSumoCanvas(container, state); }
