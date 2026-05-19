let map, markersLayer;
let currentFilter = 'all';
let allFeatures = [];

const TYPE_CONFIG = {
  new:          { color: '#FFFFFF', label: 'Chưa mua hàng',    bg: '#374151', text: '#9CA3AF' },
  retail:       { color: '#22C55E', label: 'Cửa hàng bán lẻ', bg: '#14532D', text: '#86EFAC' },
  agent:        { color: '#EAB308', label: 'Đại lý',           bg: '#713F12', text: '#FDE047' },
  distributor:  { color: '#EF4444', label: 'Nhà phân phối',    bg: '#7F1D1D', text: '#FCA5A5' },
};

function initMap() {
  map = L.map('map', { center: [10.8231, 106.6297], zoom: 13 });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors', maxZoom: 19,
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);
  map.on('click', closeSheet);
}

// ── Build icon HTML theo activity ────────────────────────────
function buildMarkerHtml(color, activity, type) {
  const border = type === 'new' ? 'border:2px solid #888;' : '';

  switch(activity) {

    case 'both':
      return `<div style="
        width:28px;height:28px;cursor:pointer;
        display:flex;align-items:center;justify-content:center;
        filter:drop-shadow(0 2px 4px rgba(0,0,0,.5));
      ">
        <svg viewBox="0 0 24 24" width="28" height="28">
          <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"
            fill="${color}" stroke="rgba(0,0,0,0.3)" stroke-width="1.5"/>
        </svg>
      </div>`;

    case 'checkin':
      return `<div style="position:relative;width:28px;height:38px;cursor:pointer">
        <div style="position:absolute;left:11px;bottom:0;width:3px;height:36px;background:#555;border-radius:2px"></div>
        <div style="position:absolute;left:14px;top:0;width:14px;height:11px;background:${color};border:1.5px solid rgba(0,0,0,0.3);clip-path:polygon(0 0,100% 15%,100% 85%,0 100%);border-radius:1px"></div>
        <div style="position:absolute;left:6px;bottom:-3px;width:12px;height:4px;background:rgba(0,0,0,0.2);border-radius:50%;filter:blur(2px)"></div>
      </div>`;

    case 'call':
      return `<div style="position:relative;width:28px;height:28px;cursor:pointer">
        <div style="
          width:26px;height:26px;border-radius:50%;
          background:${color};
          border:2.5px solid rgba(0,0,0,0.25);
          box-shadow:0 2px 6px rgba(0,0,0,.4);
          display:flex;align-items:center;justify-content:center;
        ">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="rgba(0,0,0,0.7)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.61 3.35 2 2 0 0 1 3.6 1h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.6a16 16 0 0 0 5.55 5.55l.96-.96a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
          </svg>
        </div>
      </div>`;

    default:
      return `<div style="
        width:22px;height:22px;border-radius:50%;
        background:${color};${border}
        border:${type==='new'?'2px solid #888':'3px solid rgba(0,0,0,0.25)'};
        box-shadow:0 2px 6px rgba(0,0,0,.35);cursor:pointer;
      "></div>`;
  }
}

function buildMarker(feature) {
  const p = feature.properties;
  const [lon, lat] = feature.geometry.coordinates;
  const act = p.activity || 'none';

  const sizes   = { both:[28,28], checkin:[28,38], call:[26,26], none:[22,22] };
  const anchors = { both:[14,14], checkin:[11,38], call:[13,13], none:[11,11] };

  const icon = L.divIcon({
    className: '',
    html: buildMarkerHtml(p.color, act, p.type),
    iconSize:   sizes[act],
    iconAnchor: anchors[act],
  });

  const marker = L.marker([lat, lon], { icon });
  marker.on('click', e => {
    e.originalEvent.stopPropagation();
    // FIX: spread toàn bộ properties thay vì destructure thủ công
    // đảm bảo last_checkin, last_call và tất cả field khác đều được pass
    openStoreSheet({ ...p, activity: act }, [lon, lat]);
  });
  marker._storeId   = p.id;
  marker._storeType = p.type;
  return marker;
}

function renderMarkers(features) {
  markersLayer.clearLayers();
  features
    .filter(f => currentFilter === 'all' || f.properties.type === currentFilter)
    .forEach(f => markersLayer.addLayer(buildMarker(f)));
}

function filterType(btn) {
  document.querySelectorAll('.filter-pills .pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  currentFilter = btn.dataset.type;
  renderMarkers(allFeatures);
  renderStoreList(allFeatures);
}

function flyToStore(lat, lon) {
  map.flyTo([lat, lon], 17, { animate: true, duration: .8 });
}

async function loadMapData() {
  try {
    const geojson = await api.storesGeoJSON();
    allFeatures = geojson.features || [];
    renderMarkers(allFeatures);
    renderStoreList(allFeatures);
    updateStats();
    navigator.geolocation?.getCurrentPosition(pos => {
      map.setView([pos.coords.latitude, pos.coords.longitude], 14);
    });
  } catch (e) {
    showToast('Không tải được dữ liệu bản đồ: ' + e.message, 'error');
  }
}

function updateStats() {
  document.getElementById('stat-total').textContent = allFeatures.length;
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('stat-today').textContent = allFeatures.filter(f =>
    f.properties.last_checkin?.slice(0, 10) === today).length;
  document.getElementById('stat-pending').textContent = allFeatures.filter(f =>
    f.properties.activity === 'none').length;
}