'use strict';

// ── Map init ──────────────────────────────────────────────────────────────────
const map = L.map('map', { zoomControl: false }).setView([62, 15], 5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 18,
}).addTo(map);
L.control.zoom({ position: 'bottomright' }).addTo(map);

// ── State ─────────────────────────────────────────────────────────────────────
let fireLayer = L.layerGroup().addTo(map);
let currentStatus = 'active';

// ── Panel helpers ─────────────────────────────────────────────────────────────
const backdrop = document.getElementById('backdrop');

function openPanel(id) {
  document.getElementById(id).classList.remove('hidden');
  backdrop.classList.remove('hidden');
}
function closePanel(id) {
  document.getElementById(id).classList.add('hidden');
  backdrop.classList.add('hidden');
}

document.querySelectorAll('.close-btn').forEach(btn => {
  btn.addEventListener('click', () => closePanel(btn.dataset.close));
});
backdrop.addEventListener('click', () => {
  ['filter-panel', 'log-panel', 'detail-panel'].forEach(closePanel);
});

document.getElementById('btn-filter').addEventListener('click', () => openPanel('filter-panel'));
document.getElementById('btn-log').addEventListener('click', () => {
  loadLog();
  openPanel('log-panel');
});

// ── Fire colour / size by intensity (FRP) ────────────────────────────────────
function markerStyle(fire) {
  const frp = fire.max_frp || 0;
  const isActive = fire.status === 'active';

  let color;
  if (!isActive)          color = '#666';
  else if (frp > 100)     color = '#ff1100';
  else if (frp > 30)      color = '#ff6600';
  else if (frp > 5)       color = '#ffaa00';
  else                    color = '#ffdd33';

  const size = isActive
    ? Math.max(10, Math.min(28, 10 + Math.sqrt(frp) * 2))
    : 8;

  return { color, size };
}

// ── Render fires on map ───────────────────────────────────────────────────────
function renderFires(geojson) {
  fireLayer.clearLayers();
  (geojson.features || []).forEach(f => {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    const { color, size } = markerStyle(p);

    const icon = L.divIcon({
      className: '',
      html: `<div class="fire-marker" style="width:${size}px;height:${size}px;background:${color};opacity:${p.status==='active'?1:0.55}"></div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });

    const marker = L.marker([lat, lon], { icon });
    marker.on('click', () => showDetail(p.fire_id));
    fireLayer.addLayer(marker);
  });
}

// ── Fetch & display fires ─────────────────────────────────────────────────────
async function loadFires(params = {}) {
  const qs = new URLSearchParams();
  if (params.status)  qs.set('status', params.status);
  if (params.from)    qs.set('from', params.from);
  if (params.to)      qs.set('to', params.to);

  try {
    const resp = await fetch(`/fires?${qs}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderFires(data);
  } catch (err) {
    console.error('Failed to load fires', err);
  }
}

// ── Fire detail ───────────────────────────────────────────────────────────────
function fmt(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return d.toLocaleString('sv-SE', { dateStyle: 'short', timeStyle: 'short' });
}

function durLabel(h) {
  if (!h || h < 1) return '<1 timme';
  if (h < 24) return `${Math.round(h)} timmar`;
  return `${(h / 24).toFixed(1)} dagar`;
}

async function showDetail(fireId) {
  const resp = await fetch(`/fires/${fireId}`);
  if (!resp.ok) return;
  const f = await resp.json();
  const p = f.properties;

  const badge = p.status === 'active'
    ? '<span class="badge-active">Aktiv</span>'
    : '<span class="badge-inactive">Inaktiv</span>';

  document.getElementById('detail-body').innerHTML = `
    <div class="detail-row"><span class="detail-label">Status</span><span class="detail-value">${badge}</span></div>
    <div class="detail-row"><span class="detail-label">Första detektion</span><span class="detail-value">${fmt(p.first_seen)}</span></div>
    <div class="detail-row"><span class="detail-label">Senast synlig</span><span class="detail-value">${fmt(p.last_seen)}</span></div>
    <div class="detail-row"><span class="detail-label">Varaktighet</span><span class="detail-value">${durLabel(p.duration_hours)}</span></div>
    <div class="detail-row"><span class="detail-label">Satellitdetektioner</span><span class="detail-value">${p.detections}</span></div>
    <div class="detail-row"><span class="detail-label">Max intensitet (FRP)</span><span class="detail-value">${p.max_frp ? p.max_frp.toFixed(1) + ' MW' : '—'}</span></div>
    <div class="detail-row"><span class="detail-label">Position</span><span class="detail-value">${f.geometry.coordinates[1].toFixed(4)}°N, ${f.geometry.coordinates[0].toFixed(4)}°E</span></div>
    <p style="font-size:.75rem;color:var(--color-muted);margin-top:8px">
      Satellitdata från NASA FIRMS/VIIRS. Visar värmesignaturer — ej verifierade brandrapporter.
    </p>`;

  openPanel('detail-panel');
}

// ── Ingestion log ─────────────────────────────────────────────────────────────
async function loadLog() {
  const container = document.getElementById('log-entries');
  container.innerHTML = '<p style="color:var(--color-muted)">Laddar…</p>';

  try {
    const resp = await fetch('/ingestion-log');
    const data = await resp.json();

    // Update stale banner
    const banner = document.getElementById('stale-banner');
    if (data.data_stale) {
      banner.classList.remove('hidden');
      document.getElementById('stale-time').textContent =
        data.last_success ? fmt(data.last_success) : 'aldrig';
    } else {
      banner.classList.add('hidden');
    }

    if (!data.entries.length) {
      container.innerHTML = '<p style="color:var(--color-muted)">Ingen hämtning utförd ännu.</p>';
      return;
    }

    container.innerHTML = data.entries.map(e => {
      const cls = e.succeeded ? 'ok' : 'fail';
      const status = e.succeeded ? '✓ Lyckades' : '✗ Misslyckades';
      const detail = e.succeeded
        ? `${e.detections_fetched ?? 0} detektioner → ${e.fires_updated ?? 0} bränder`
        : `Felkod: ${e.error_code || '?'} — ${e.error_message || ''}`;
      const human = !e.succeeded && e.human_explanation
        ? `<div class="log-human">💡 ${e.human_explanation}</div>`
        : '';
      return `<div class="log-entry ${cls}">
        <div class="log-time">${fmt(e.attempted_at)}</div>
        <div class="log-status">${status}</div>
        <div class="log-detail">${detail}</div>
        ${human}
      </div>`;
    }).join('');

  } catch (err) {
    container.innerHTML = `<p style="color:var(--color-accent)">Kunde inte hämta logg: ${err.message}</p>`;
  }
}

// ── Check stale on load ───────────────────────────────────────────────────────
async function checkStale() {
  try {
    const resp = await fetch('/ingestion-log?limit=1');
    const data = await resp.json();
    const banner = document.getElementById('stale-banner');
    if (data.data_stale) {
      banner.classList.remove('hidden');
      document.getElementById('stale-time').textContent =
        data.last_success ? fmt(data.last_success) : 'aldrig';
    }
  } catch (_) {}
}

// ── Filter apply ──────────────────────────────────────────────────────────────
document.getElementById('btn-apply-filter').addEventListener('click', () => {
  const status = document.getElementById('filter-status').value;
  const from   = document.getElementById('filter-from').value;
  const to     = document.getElementById('filter-to').value;
  closePanel('filter-panel');
  loadFires({
    status: status || undefined,
    from:   from   ? from + 'T00:00:00' : undefined,
    to:     to     ? to   + 'T23:59:59' : undefined,
  });
});

// ── Boot ──────────────────────────────────────────────────────────────────────
loadFires({ status: 'active' });
checkStale();
