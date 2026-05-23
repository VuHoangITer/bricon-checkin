// app.js - main app logic

let currentUser = null;
let selectedStore = null;
let checkinGPS = null;
let newStoreGPS = null;

// ─────────────────────────────────────────
// AUTH
// ─────────────────────────────────────────
function doLogout() {
  clearToken();
  currentUser = null;
  window.location.href = '/login';
}

function showLogin() {
  window.location.href = '/login';
}

async function startApp() {
  document.getElementById('user-badge').textContent = currentUser?.full_name || '';

  if (currentUser?.role === 'telesales') {
    const btnAdd = document.querySelector('.btn-add-store');
    if (btnAdd) btnAdd.style.display = 'none';
  }

  if (window.innerWidth <= 768) {
    sidebarOpen = false;
    document.getElementById('sidebar').classList.add('collapsed');
  } else {
    sidebarOpen = true;
    document.getElementById('sidebar').classList.remove('collapsed');
  }

  initMap();
  await loadMapData();
  await loadActiveSession();
}

window.addEventListener('DOMContentLoaded', async () => {
  const token = localStorage.getItem('sf_token');
  if (!token) { window.location.href = '/login'; return; }

  const cached = localStorage.getItem('sf_user');
  if (cached) {
    try { currentUser = JSON.parse(cached); } catch {}
  }

  try {
    const user = await api.me();
    currentUser = user;
    localStorage.setItem('sf_user', JSON.stringify(user));
    startApp();
  } catch { doLogout(); }
});

// ─────────────────────────────────────────
// SIDEBAR
// ─────────────────────────────────────────
let sidebarOpen = true;

function toggleSidebar() {
  sidebarOpen = !sidebarOpen;
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.toggle('collapsed', !sidebarOpen);

  const onEnd = () => {
    if (map) map.invalidateSize();
    sidebar.removeEventListener('transitionend', onEnd);
  };
  sidebar.addEventListener('transitionend', onEnd);
  setTimeout(() => { if (map) map.invalidateSize(); }, 350);

  if (window.innerWidth <= 768) {
    let overlay = document.getElementById('sidebar-overlay');
    if (sidebarOpen) {
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'sidebar-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:199;';
        overlay.onclick = () => toggleSidebar();
        document.querySelector('.app-body').appendChild(overlay);
      }
    } else {
      if (overlay) overlay.remove();
    }
  }
}

window.addEventListener('resize', () => {
  // Bỏ qua resize do bàn phím ảo (chỉ thay đổi chiều cao, không thay đổi chiều rộng)
  if (window.innerWidth <= 768 && sidebarOpen) {
    // Kiểm tra xem có element nào đang được focus không (bàn phím đang mở)
    const active = document.activeElement;
    const isKeyboardOpen = active && (
      active.tagName === 'INPUT' ||
      active.tagName === 'TEXTAREA' ||
      active.tagName === 'SELECT'
    );
    if (isKeyboardOpen) return; // Bàn phím vừa mở → bỏ qua
    sidebarOpen = false;
    document.getElementById('sidebar').classList.add('collapsed');
    const overlay = document.getElementById('sidebar-overlay');
    if (overlay) overlay.remove();
  }
});

// Cache cửa hàng chưa có tọa độ để dùng trong sidebar
let _noCoordsStores = [];

// Gọi khi loadMapData xong để load thêm store không có tọa độ
async function loadNoCoordsForSidebar() {
  try {
    const token = localStorage.getItem('sf_token');
    const res = await fetch('/api/stores/no-coords', {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(r => r.json());
    _noCoordsStores = Array.isArray(res) ? res : [];
  } catch {
    _noCoordsStores = [];
  }
  renderStoreList(allFeatures);
}

function renderStoreList(features) {
  const el = document.getElementById('store-list');

  const TYPE_COLORS = { retail:'#22C55E', agent:'#EAB308', distributor:'#EF4444', new:'#9CA3AF' };

  // Lọc store có tọa độ theo filter
  const filtered = features.filter(f =>
    currentFilter === 'all' || currentFilter === 'no-coords' || f.properties.type === currentFilter
  );

  // Store chưa có tọa độ — hiện khi filter = all hoặc no-coords
  const noCoords = (currentFilter === 'all' || currentFilter === 'no-coords')
    ? _noCoordsStores
    : [];

  if (!filtered.length && !noCoords.length) {
    el.innerHTML = '<div style="padding:12px;color:var(--text2);font-size:12px;">Không có cửa hàng</div>';
    return;
  }

  // Render store chưa có tọa độ — nổi bật, nằm ĐẦU TIÊN
  const noCoordsHtml = noCoords.map(s => {
    const color = TYPE_COLORS[s.type] || '#9CA3AF';
    const cfg   = TYPE_CONFIG[s.type] || TYPE_CONFIG.new;
    return `<div class="store-item" onclick="selectNoCoordsStoreFromList('${s.id}','${s.name.replace(/'/g,"\'")}','${s.code}','${s.type}')"
      style="border-left:3px solid var(--warn);background:rgba(234,179,8,0.06)">
      <div class="store-item-dot" style="background:${color};${s.type==='new'?'border:1.5px solid #666':''}"></div>
      <div class="store-item-info" style="flex:1;min-width:0">
        <div class="store-item-name">${s.name}</div>
        <div class="store-item-meta">${s.code} · ${cfg.label}</div>
      </div>
      <span style="flex-shrink:0;font-size:10px;font-weight:600;color:var(--warn);
                   background:rgba(234,179,8,0.15);padding:2px 6px;border-radius:4px">📍 Chưa có</span>
    </div>`;
  }).join('');

  // Header phân tách nếu có cả 2 nhóm và filter = all
  const separator = (noCoordsHtml && filtered.length && currentFilter === 'all')
    ? `<div style="font-size:10px;font-weight:600;color:var(--text2);text-transform:uppercase;
         letter-spacing:.5px;padding:8px 14px 4px;border-top:1px solid var(--border)">
         Đã có tọa độ
       </div>`
    : '';

  // Render store có tọa độ (ẩn khi filter = no-coords)
  const withCoordsHtml = currentFilter === 'no-coords' ? '' :
    filtered.slice(0, 50).map(f => {
      const p = f.properties;
      const cfg = TYPE_CONFIG[p.type] || TYPE_CONFIG.new;
      return `<div class="store-item" onclick="selectStoreFromList('${p.id}')">
        <div class="store-item-dot" style="background:${p.color};${p.type==='new'?'border:1.5px solid #666':''}"></div>
        <div class="store-item-info">
          <div class="store-item-name">${p.name}</div>
          <div class="store-item-meta">${p.code} · ${cfg.label}</div>
        </div>
      </div>`;
    }).join('');

  el.innerHTML = noCoordsHtml + separator + withCoordsHtml;
}

// Bấm vào store chưa có tọa độ trong sidebar → mở bottom sheet (không mở modal)
async function selectNoCoordsStoreFromList(id, name, code, type) {
  const TYPE_CONFIG_LOCAL = {
    new:         { color:'#FFFFFF', label:'Chưa mua hàng',    bg:'#374151', text:'#9CA3AF' },
    retail:      { color:'#22C55E', label:'Cửa hàng bán lẻ', bg:'#14532D', text:'#86EFAC' },
    agent:       { color:'#EAB308', label:'Đại lý',           bg:'#713F12', text:'#FDE047' },
    distributor: { color:'#EF4444', label:'Nhà phân phối',    bg:'#7F1D1D', text:'#FCA5A5' },
  };

  // Fetch đầy đủ thông tin
  let storeProps = { id, name, code, type, address:'', owner:'', phone:'',
    last_checkin:null, last_call:null, activity:'none', _coords:[null,null],
    ...TYPE_CONFIG_LOCAL[type] };
  try {
    const token = localStorage.getItem('sf_token');
    const res = await fetch(`/api/stores/${id}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(r => r.json());
    const p = res.properties || {};
    storeProps = {
      ...storeProps,
      name:    p.name    || name,
      code:    p.code    || code,
      type:    p.type    || type,
      address: p.address || '',
      owner:   p.owner   || '',
      phone:   p.phone   || '',
      last_checkin: p.last_checkin || null,
      last_call:    p.last_call    || null,
      ...TYPE_CONFIG_LOCAL[p.type || type],
    };
  } catch {}

  // Mở bottom sheet bình thường — nút "Đặt vị trí" sẽ tự hiện trong sheet-location-btns
  openStoreSheet(storeProps, [null, null]);
}

function searchStores(q) {
  const lower = q.toLowerCase();
  const filtered = q ? allFeatures.filter(f =>
    f.properties.name.toLowerCase().includes(lower) ||
    f.properties.code.toLowerCase().includes(lower)
  ) : allFeatures;
  if (q) {
    const orig = _noCoordsStores;
    _noCoordsStores = orig.filter(s =>
      s.name.toLowerCase().includes(lower) || s.code.toLowerCase().includes(lower)
    );
    renderStoreList(filtered);
    _noCoordsStores = orig;
  } else {
    renderStoreList(filtered);
  }
}

function selectStoreFromList(storeId) {
  const feature = allFeatures.find(f => f.properties.id === storeId);
  if (!feature) return;
  const [lon, lat] = feature.geometry.coordinates;
  flyToStore(lat, lon, storeId);
  openStoreSheet({ ...feature.properties, activity: feature.properties.activity || 'none' }, [lon, lat]);
}

function searchStores(q) {
  const lower = q.toLowerCase();
  const filtered = q ? allFeatures.filter(f =>
    f.properties.name.toLowerCase().includes(lower) ||
    f.properties.code.toLowerCase().includes(lower)
  ) : allFeatures;
  // Cũng lọc _noCoordsStores theo từ khoá
  if (q) {
    const orig = _noCoordsStores;
    _noCoordsStores = orig.filter(s =>
      s.name.toLowerCase().includes(lower) || s.code.toLowerCase().includes(lower)
    );
    renderStoreList(filtered);
    _noCoordsStores = orig; // restore
  } else {
    renderStoreList(filtered);
  }
}

// ─────────────────────────────────────────
// STORE BOTTOM SHEET
// ─────────────────────────────────────────
function openStoreSheet(props, coords) {
  selectedStore = props;
  props._coords = coords || [null, null];
  const cfg = TYPE_CONFIG[props.type] || TYPE_CONFIG.new;
  document.getElementById('sheet-name').textContent = props.name;
  document.getElementById('sheet-code').textContent = props.code;
  document.getElementById('sheet-address').textContent = props.address || 'Chưa có địa chỉ';
  document.getElementById('sheet-owner').textContent = props.owner || '—';
  document.getElementById('sheet-phone').textContent = props.phone || '—';

  const [lon, lat] = props._coords || [null, null];
  const coordEl = document.getElementById('sheet-coords');
  const gmapBtn = document.getElementById('sheet-gmap-btn');
  if (lat && lon) {
    coordEl.textContent = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
    coordEl.style.display = '';
    gmapBtn.style.display = '';
    gmapBtn.onclick = () => window.open(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`, '_blank');
  } else {
    coordEl.style.display = 'none';
    gmapBtn.style.display = 'none';
  }

  const lastCI = props.last_checkin
    ? `Check-in cuối: ${formatDateOnly(props.last_checkin)}`
    : 'Chưa check-in lần nào';
  document.getElementById('sheet-last-checkin').textContent = lastCI;

  _renderCareStatus(props);

  const badge = document.getElementById('sheet-type-badge');
  badge.textContent = cfg.label;
  badge.style.background = cfg.bg;
  badge.style.color = cfg.text;

  document.getElementById('fab-checkin').classList.add('hidden');
  document.getElementById('store-sheet').classList.remove('hidden');

  const btnCI   = document.getElementById('sheet-btn-checkin');
  const btnCall = document.getElementById('sheet-btn-call');
  const role = currentUser?.role || JSON.parse(localStorage.getItem('sf_user') || '{}').role || '';
  if (btnCI)   btnCI.style.display   = (role === 'telesales') ? 'none' : '';
  if (btnCall) btnCall.style.display = '';

  // ── Nút vị trí ──────────────────────────────────────────
  _renderLocationBtns(props, coords);

  loadStoreHistory(props.id);
}

function _renderCareStatus(props) {
  const el = document.getElementById('sheet-care-status');
  if (!el) return;

  const now = new Date();
  const lines = [];

  // ── Check-in ──────────────────────────────────────────────
  if (props.last_checkin) {
    const raw = props.last_checkin;
    // Nếu chỉ có DATE string (yyyy-mm-dd), parse theo giờ VN tránh lệch UTC
    const last = raw.includes('T')
      ? new Date(raw)
      : new Date(raw + 'T00:00:00+07:00');
    const deadline = new Date(last);
    deadline.setDate(deadline.getDate() + (checkinActivityDays || 7));
    const daysLeft = Math.ceil((deadline - now) / 86400000);

    if (daysLeft <= 0) {
      lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--danger)">
        🚩 <span>Cần check-in lại <strong>(quá hạn ${Math.abs(daysLeft)} ngày)</strong></span>
      </div>`);
    } else if (daysLeft <= 2) {
      lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--warn)">
        🚩 <span>Cần check-in lại trong vòng <strong>${daysLeft} ngày tới</strong></span>
      </div>`);
    } else {
      lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--success)">
        🚩 <span>Check-in còn hiệu lực <strong>${daysLeft} ngày</strong></span>
      </div>`);
    }
  } else {
    lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2)">
      🚩 <span>Chưa check-in lần nào</span>
    </div>`);
  }

  // ── Gọi điện ──────────────────────────────────────────────
  if (props.last_call) {
    const last = new Date(props.last_call);
    const deadline = new Date(last);
    deadline.setDate(deadline.getDate() + (callActivityDays || 7));
    const daysLeft = Math.ceil((deadline - now) / 86400000);

    if (daysLeft <= 0) {
      lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--danger)">
        📞 <span>Cần gọi lại <strong>(quá hạn ${Math.abs(daysLeft)} ngày)</strong></span>
      </div>`);
    } else if (daysLeft <= 2) {
      lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--warn)">
        📞 <span>Gọi lại trong vòng <strong>${daysLeft} ngày tới</strong></span>
      </div>`);
    } else {
      lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--success)">
        📞 <span>Gọi điện còn hiệu lực <strong>${daysLeft} ngày</strong></span>
      </div>`);
    }
  } else {
    lines.push(`<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2)">
      📞 <span>Chưa gọi điện lần nào</span>
    </div>`);
  }

  el.innerHTML = lines.join('');
}

function closeSheet() {
  document.getElementById('store-sheet').classList.add('hidden');
  document.getElementById('fab-checkin').classList.add('hidden');
  selectedStore = null;
}

async function loadStoreHistory(storeId) {
  const el = document.getElementById('sheet-history');
  el.innerHTML = '<div style="font-size:12px;color:var(--text2);padding:8px 0">Đang tải...</div>';
  try {
    const [checkinRes, callRes] = await Promise.all([
      api.history({ store_id: storeId, limit: 5 }),
      fetch(`/api/calls/history?store_id=${storeId}&limit=5`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('sf_token')}` }
      }).then(r => r.json()).catch(() => ({ data: [] })),
    ]);

    const checkins = checkinRes.data || [];
    const calls    = callRes.data    || [];

    if (!checkins.length && !calls.length) {
      el.innerHTML = '<div style="font-size:12px;color:var(--text2);padding:8px 0">Chưa có hoạt động nào</div>';
      return;
    }

    let html = '';

    if (checkins.length) {
      html += `<div class="sidebar-label" style="margin-bottom:8px;margin-top:4px">📍 Lịch sử check-in</div>`;
      html += checkins.map(c => {
        const photos = [];
        if (c.photo_url)  photos.push(c.photo_url);
        if (c.photo2_url) photos.push(c.photo2_url);
        if (c.photo_public_id) {
          const extra = c.photo_public_id.split('|').filter(u => u && u !== c.photo2_url);
          photos.push(...extra);
        } else if (c.photo3_url && !photos.includes(c.photo3_url)) {
          photos.push(c.photo3_url);
        }

        const photosHtml = photos.length ? `
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
            ${photos.map(url => `
              <div onclick="openImageFull('${url}')" style="
                width:64px;height:64px;border-radius:6px;overflow:hidden;
                border:1px solid var(--border);cursor:zoom-in;flex-shrink:0;
                background:var(--surface2);
              ">
                <img src="${url}" style="width:100%;height:100%;object-fit:cover" loading="lazy">
              </div>
            `).join('')}
          </div>` : '';

        return `<div class="history-item">
          <div class="history-item-header">
            <span>${c.user_name}</span>
            <span>${formatDate(c.checkin_at)}</span>
          </div>
          ${c.description ? `<div class="history-desc">${c.description}</div>` : ''}
          ${c.duration_min ? `<div class="history-meta">⏱ ${c.duration_min} phút</div>` : ''}
          ${photosHtml}
        </div>`;
      }).join('');
    }

    if (calls.length) {
      html += `<div class="sidebar-label" style="margin-bottom:8px;margin-top:12px">📞 Lịch sử gọi điện</div>`;
      html += calls.map(c => `<div class="history-item">
        <div class="history-item-header">
          <span>${c.user_name}</span>
          <span>${formatDate(c.called_at)}</span>
        </div>
        ${c.note ? `<div class="history-desc">${c.note}</div>` : '<div class="history-meta" style="color:var(--text2)">Không có ghi chú</div>'}
      </div>`).join('');
    }

    el.innerHTML = html;
  } catch { el.innerHTML = ''; }
}

// ─────────────────────────────────────────
// CHECK-IN
// ─────────────────────────────────────────
function startCheckinFromSheet() {
  const store = selectedStore;

  // Bắt buộc đặt vị trí trước khi check-in
  const hasCoords = store._coords && store._coords[0] != null && store._coords[1] != null;
  if (!hasCoords) {
    showToast('Cần đặt vị trí cửa hàng trước khi check-in', 'error');
    // Cuộn xuống nút "Đặt vị trí ngay" trong bottom sheet
    document.getElementById('sheet-location-btns')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }

  closeSheet();
  selectedStore = store;
  openCheckinModal();
}

function openCheckinModal() {
  if (!selectedStore) return;
  if (typeof activeSession !== 'undefined' && activeSession) {
    showWorkingScreen(activeSession);
    return;
  }
  document.getElementById('ci-store-name').textContent = `Check-in: ${selectedStore.name}`;
  document.getElementById('ci-gps-status').textContent = '📡 Sẽ lấy GPS khi xác nhận...';
  document.getElementById('ci-gps-status').className = 'gps-status';
  document.getElementById('ci-min-time').textContent = minMinutes + ' phút';
  document.getElementById('modal-checkin-start').classList.remove('hidden');
}

function confirmStartCheckin() {
  if (!selectedStore) return;
  document.getElementById('btn-start-checkin').disabled = true;
  document.getElementById('btn-start-checkin').textContent = 'Đang xử lý...';
  startCheckin(selectedStore.id, selectedStore.name).finally(() => {
    document.getElementById('btn-start-checkin').disabled = false;
    document.getElementById('btn-start-checkin').textContent = '📍 Bắt đầu Check-in';
  });
}

function triggerCamera() { document.getElementById('photo-input').click(); }

function handlePhoto(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const img = document.getElementById('photo-preview');
    img.src = e.target.result;
    img.classList.remove('hidden');
    document.getElementById('photo-placeholder').classList.add('hidden');
  };
  reader.readAsDataURL(file);
}

async function submitCheckin() {
  if (!checkinGPS) { showToast('Cần có GPS để check-in', 'error'); return; }
  const btn = document.getElementById('btn-submit-checkin');
  btn.disabled = true; btn.textContent = 'Đang gửi...';
  try {
    const fd = new FormData();
    fd.append('store_id', selectedStore.id);
    fd.append('latitude', checkinGPS.lat);
    fd.append('longitude', checkinGPS.lon);
    fd.append('accuracy', checkinGPS.acc);
    fd.append('description', document.getElementById('checkin-desc').value);
    fd.append('duration', document.getElementById('checkin-duration').value);
    const photo = document.getElementById('photo-input').files[0];
    if (photo) fd.append('photo', photo);
    const res = await api.checkin(fd);
    closeModal('modal-checkin');
    showToast(res.message || 'Check-in thành công!', 'success');
    loadMapData();
  } catch (e) { showToast(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Xác nhận check-in'; }
}

// ─────────────────────────────────────────
// ADD STORE
// ─────────────────────────────────────────
let _nameCheckTimer = null;

function openAddStoreModal() {
  document.getElementById('new-store-name').value     = '';
  document.getElementById('new-store-code').value     = '';
  document.getElementById('new-store-code').placeholder = 'Tự động';
  document.getElementById('new-store-type').value     = 'new';
  document.getElementById('new-store-owner').value    = '';
  document.getElementById('new-store-phone').value    = '';
  document.getElementById('new-store-address').value  = '';
  document.getElementById('new-store-ward').value     = '';
  document.getElementById('new-store-district').value = '';
  document.getElementById('new-store-province').value = 'TP.HCM';
  document.getElementById('new-store-lat').value      = '';
  document.getElementById('new-store-lon').value      = '';
  document.getElementById('new-store-gps').textContent = '📡 Đang lấy GPS tự động...';
  document.getElementById('new-store-gps').className  = 'gps-status';
  document.getElementById('name-check-msg').textContent = '';
  newStoreGPS = null;
  _fetchAutoCode('new');
  document.getElementById('modal-add-store').classList.remove('hidden');

  // Tự động lấy GPS ngay khi mở form
  captureGpsForNewStore();
}

async function _fetchAutoCode(storeType) {
  try {
    const res = await api.autoCode(storeType);
    document.getElementById('new-store-code').placeholder = res.code;
    document.getElementById('new-store-code').dataset.autoCode = res.code;
  } catch {}
}

async function onStoreTypeChange(sel) {
  await _fetchAutoCode(sel.value);
}

async function onStoreNameInput(input) {
}

function captureGpsForNewStore() {
  const el = document.getElementById('new-store-gps');
  el.textContent = '📡 Đang lấy GPS...';
  el.className = 'gps-status';
  navigator.geolocation.getCurrentPosition(
    pos => {
      newStoreGPS = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      document.getElementById('new-store-lat').value = newStoreGPS.lat;
      document.getElementById('new-store-lon').value = newStoreGPS.lon;
      el.textContent = `✅ ${newStoreGPS.lat.toFixed(6)}, ${newStoreGPS.lon.toFixed(6)} (±${Math.round(pos.coords.accuracy)}m)`;
      el.className = 'gps-status ok';
    },
    err => { el.textContent = '❌ Không lấy được GPS'; el.className = 'gps-status err'; },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
  );
}

async function submitNewStore() {
  const name = document.getElementById('new-store-name').value.trim();
  const type = document.getElementById('new-store-type').value;
  if (!name) { showToast('Cần nhập tên cửa hàng', 'error'); return; }

  const lat = parseFloat(document.getElementById('new-store-lat').value);
  const lon = parseFloat(document.getElementById('new-store-lon').value);

  // Cảnh báo nếu có cửa hàng gần trong vòng 30m
  if (lat && lon) {
    const nearby = _findNearbyStores(lat, lon, 30);
    if (nearby.length) {
      const names = nearby.map(s => `• ${s.name} (${s.code}) — cách ${s.dist}m`).join('\n');
      const ok = confirm(`⚠️ Có ${nearby.length} cửa hàng trong vòng 30m:\n${names}\n\nBạn có chắc muốn tạo cửa hàng mới không?`);
      if (!ok) return;
    }
  }

  try {
    const payload = {
      store_name: name,
      store_type: type,
      owner_name: document.getElementById('new-store-owner').value.trim(),
      phone:      document.getElementById('new-store-phone').value.trim(),
      address:    document.getElementById('new-store-address').value.trim(),
      ward:       document.getElementById('new-store-ward').value.trim(),
      district:   document.getElementById('new-store-district').value.trim(),
      province:   document.getElementById('new-store-province').value.trim(),
      latitude:   parseFloat(document.getElementById('new-store-lat').value) || null,
      longitude:  parseFloat(document.getElementById('new-store-lon').value) || null,
    };
    const manualCode = document.getElementById('new-store-code').value.trim().toUpperCase();
    if (manualCode) payload.store_code = manualCode;
    await api.createStore(payload);
    closeModal('modal-add-store');
    showToast(`Đã tạo cửa hàng ${name}`, 'success');
    loadMapData();
  } catch (e) { showToast(e.message, 'error'); }
}

// ─────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 3500);
}

function formatDateOnly(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('T')[0].split('-');
  return `${d}/${m}/${y}`;
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Ho_Chi_Minh'
  });
}

function openImageFull(url) {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.95);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:zoom-out;padding:16px;';
  overlay.onclick = () => overlay.remove();
  const img = document.createElement('img');
  img.src = url;
  img.style.cssText = 'max-width:100%;max-height:100vh;object-fit:contain;border-radius:8px;';
  overlay.appendChild(img);
  document.body.appendChild(overlay);
}

// ─────────────────────────────────────────
// ĐỔI LOẠI CỬA HÀNG
// ─────────────────────────────────────────
function openChangeTypeModal() {
  if (!selectedStore) return;
  document.getElementById('change-type-current').textContent = TYPE_CONFIG[selectedStore.type]?.label || selectedStore.type;
  document.getElementById('change-type-select').value = selectedStore.type;
  document.getElementById('modal-change-type').classList.remove('hidden');
}

async function submitChangeType() {
  const newType = document.getElementById('change-type-select').value;
  if (!selectedStore) return;
  try {
    await api.updateStore(selectedStore.id, { store_type: newType });
    closeModal('modal-change-type');
    showToast('Đã cập nhật loại cửa hàng', 'success');
    loadMapData();
    closeSheet();
  } catch(e) { showToast(e.message, 'error'); }
}

// ─────────────────────────────────────────
// GỌI ĐIỆN
// ─────────────────────────────────────────
function openCallModal() {
  if (!selectedStore) return;
  document.getElementById('call-store-name').textContent = `📞 ${selectedStore.name}`;
  const phone = selectedStore.phone || '';
  document.getElementById('call-phone-display').textContent = phone || 'Chưa có số điện thoại';
  const link = document.getElementById('call-tel-link');
  if (phone) {
    link.href = `tel:${phone}`;
    link.style.display = 'inline-block';
  } else {
    link.style.display = 'none';
  }
  document.getElementById('call-note').value = '';
  document.getElementById('modal-call').classList.remove('hidden');
}

async function submitCallLog() {
  if (!selectedStore) return;
  const note = document.getElementById('call-note').value.trim();
  try {
    await fetch('/api/calls/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('sf_token')}`,
      },
      body: JSON.stringify({ store_id: selectedStore.id, note }),
    }).then(r => r.json());
    closeModal('modal-call');
    showToast(`Đã ghi nhận cuộc gọi đến ${selectedStore.name}`, 'success');
    loadMapData();
  } catch(e) { showToast('Lỗi ghi nhận cuộc gọi', 'error'); }
}

// ─────────────────────────────────────────
// CẬP NHẬT TỌA ĐỘ CỬA HÀNG
// ─────────────────────────────────────────

/**
 * Mở modal đặt/sửa vị trí cửa hàng.
 * action = 'set' (chưa có tọa độ) | 'fix' (sai tọa độ)
 */
function openLocationModal(action) {
  if (!selectedStore) return;

  const isfix = action === 'fix';
  const title = isfix ? '📍 Báo sai & sửa vị trí' : '📍 Đặt vị trí cửa hàng';

  // Thông tin cửa hàng để nhân viên xác nhận đúng chỗ
  const infoLines = [];
  if (selectedStore.address) infoLines.push(`📍 ${selectedStore.address}`);
  if (selectedStore.owner)   infoLines.push(`👤 ${selectedStore.owner}`);
  if (selectedStore.phone)   infoLines.push(`📞 ${selectedStore.phone}`);
  const infoHtml = infoLines.length
    ? `<div style="margin-top:8px;display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--text2)">${infoLines.map(l => `<span>${l}</span>`).join('')}</div>`
    : '';

  const desc = isfix
    ? `<div>Bạn đang đứng đúng tại <strong>${selectedStore.name}</strong> nhưng hệ thống báo sai vị trí.<br>Chụp 1 ảnh xác nhận rồi bấm cập nhật.</div>${infoHtml}`
    : `<div>Cửa hàng <strong>${selectedStore.name}</strong> chưa có tọa độ. Lấy GPS hiện tại của bạn để đặt vị trí.</div>${infoHtml}`;

  document.getElementById('loc-modal-title').textContent   = title;
  document.getElementById('loc-modal-desc').innerHTML      = desc;
  document.getElementById('loc-gps-status').textContent    = '📡 Chưa lấy GPS';
  document.getElementById('loc-gps-status').className      = 'gps-status';
  document.getElementById('loc-note').value                = '';
  document.getElementById('loc-photo-preview').innerHTML   = isfix ? '📷 Bấm để chụp ảnh xác nhận' : '';
  document.getElementById('loc-photo-required').style.display = isfix ? '' : 'none';
  document.getElementById('loc-action').value              = action;
  document.getElementById('loc-lat').value                 = '';
  document.getElementById('loc-lon').value                 = '';
  _locPhotoFile = null;

  // Tự động lấy GPS ngay khi mở
  _captureLocGPS();

  document.getElementById('modal-location').classList.remove('hidden');
}

let _locPhotoFile = null;

function _captureLocGPS() {
  const el = document.getElementById('loc-gps-status');
  el.textContent = '📡 Đang lấy GPS...';
  el.className   = 'gps-status';
  navigator.geolocation.getCurrentPosition(pos => {
    document.getElementById('loc-lat').value = pos.coords.latitude;
    document.getElementById('loc-lon').value = pos.coords.longitude;
    el.textContent = `✅ ${pos.coords.latitude.toFixed(6)}, ${pos.coords.longitude.toFixed(6)} (±${Math.round(pos.coords.accuracy)}m)`;
    el.className   = 'gps-status ok';
  }, () => {
    el.textContent = '❌ Không lấy được GPS — thử lại';
    el.className   = 'gps-status err';
  }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
}

function triggerLocPhoto() {
  // Hiện menu chụp / thư viện
  const existing = document.getElementById('loc-photo-menu');
  if (existing) existing.remove();
  const menu = document.createElement('div');
  menu.id = 'loc-photo-menu';
  menu.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:flex-end;justify-content:center;';
  menu.innerHTML = `
    <div style="background:var(--surface);border-radius:16px 16px 0 0;padding:16px;width:100%;max-width:480px">
      <div style="text-align:center;font-size:13px;color:var(--text2);margin-bottom:12px;font-weight:500">Ảnh xác nhận vị trí</div>
      <button onclick="_pickLocPhoto('camera')" style="display:flex;align-items:center;gap:12px;width:100%;padding:14px 16px;background:var(--surface2);border:none;border-radius:10px;margin-bottom:8px;color:var(--text);font-family:var(--font);font-size:15px;cursor:pointer">📷 <span>Chụp ảnh</span></button>
      <button onclick="_pickLocPhoto('gallery')" style="display:flex;align-items:center;gap:12px;width:100%;padding:14px 16px;background:var(--surface2);border:none;border-radius:10px;margin-bottom:8px;color:var(--text);font-family:var(--font);font-size:15px;cursor:pointer">🖼️ <span>Chọn từ thư viện</span></button>
      <button onclick="document.getElementById('loc-photo-menu').remove()" style="display:block;width:100%;padding:12px;background:transparent;border:1px solid var(--border);border-radius:10px;color:var(--text2);font-family:var(--font);font-size:14px;cursor:pointer">Huỷ</button>
    </div>`;
  menu.onclick = e => { if (e.target === menu) menu.remove(); };
  document.body.appendChild(menu);
}

function _pickLocPhoto(mode) {
  document.getElementById('loc-photo-menu')?.remove();
  let input = document.getElementById('_loc-photo-input');
  if (!input) {
    input = document.createElement('input');
    input.type = 'file'; input.id = '_loc-photo-input';
    input.accept = 'image/*'; input.style.display = 'none';
    input.onchange = () => {
      const file = input.files[0];
      if (!file) return;
      _locPhotoFile = file;
      const reader = new FileReader();
      reader.onload = e => {
        document.getElementById('loc-photo-preview').innerHTML =
          `<img src="${e.target.result}" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;border:1px solid var(--border)">`;
      };
      reader.readAsDataURL(file);
    };
    document.body.appendChild(input);
  }
  mode === 'camera' ? input.setAttribute('capture','environment') : input.removeAttribute('capture');
  input.value = '';
  input.click();
}

async function submitLocationUpdate() {
  const lat    = document.getElementById('loc-lat').value;
  const lon    = document.getElementById('loc-lon').value;
  const action = document.getElementById('loc-action').value;
  const note   = document.getElementById('loc-note').value.trim();

  if (!lat || !lon) {
    showToast('Cần lấy GPS trước', 'error'); return;
  }
  if (action === 'fix' && !_locPhotoFile) {
    showToast('Cần chụp ảnh xác nhận khi sửa vị trí', 'error'); return;
  }

  const btn = document.getElementById('btn-submit-location');
  btn.disabled = true; btn.textContent = 'Đang lưu...';

  try {
    const fd = new FormData();
    fd.append('latitude',  lat);
    fd.append('longitude', lon);
    if (note)          fd.append('note', note);
    if (_locPhotoFile) fd.append('photo', _locPhotoFile);

    const res = await fetch(`/api/stores/${selectedStore.id}/location`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('sf_token')}` },
      body: fd,
    }).then(r => r.json());

    if (res.error) { showToast(res.error, 'error'); return; }

    closeModal('modal-location');
    showToast(res.message, 'success');

    // Nếu delta lớn hơn 100m thì cảnh báo
    if (res.delta_m && res.delta_m > 100) {
      setTimeout(() => showToast(`⚠️ Vị trí lệch ${Math.round(res.delta_m)}m so với trước`, 'error'), 600);
    }

    // Reload map để cập nhật marker
    loadMapData();

    // Nếu đang mở bottom sheet thì tự động check-in luôn
    if (action === 'set' && selectedStore) {
      setTimeout(() => openCheckinModal(), 800);
    }
  } catch(e) {
    showToast('Lỗi cập nhật vị trí: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'Cập nhật vị trí';
  }
}


// ─────────────────────────────────────────
// RENDER NÚT VỊ TRÍ TRONG BOTTOM SHEET
// ─────────────────────────────────────────
function _renderLocationBtns(props, coords) {
  const el = document.getElementById('sheet-location-btns');
  if (!el) return;

  const role = currentUser?.role || JSON.parse(localStorage.getItem('sf_user') || '{}').role || '';
  // telesales không check-in nên cũng không cần sửa vị trí
  if (role === 'telesales') { el.innerHTML = ''; return; }

  const [lon, lat] = coords || [null, null];
  const hasCoords  = lat != null && lon != null;

  if (!hasCoords) {
    // Chưa có tọa độ → nút đặt vị trí nổi bật
    el.innerHTML = `
      <div style="background:rgba(234,179,8,.08);border:1px solid rgba(234,179,8,.3);
           border-radius:10px;padding:10px 12px;margin-top:4px">
        <div style="font-size:12px;color:var(--warn);font-weight:600;margin-bottom:6px">
          ⚠️ Cửa hàng này chưa có tọa độ
        </div>
        <div style="font-size:11px;color:var(--text2);margin-bottom:8px;line-height:1.5">
          Nếu bạn đang đứng tại đây, hãy đặt vị trí để check-in lần sau.
        </div>
        <button onclick="openLocationModal('set')"
          style="width:100%;padding:9px;border-radius:8px;
                 background:var(--warn);color:#000;border:none;
                 cursor:pointer;font-family:var(--font);font-size:13px;font-weight:600">
          📍 Đặt vị trí ngay
        </button>
      </div>`;
  } else {
// Đã có tọa độ → nút "Báo sai vị trí" nhỏ hơn, ít nổi bật hơn
    el.innerHTML = `
      <button onclick="openLocationModal('fix')"
        style="width:100%;padding:8px;border-radius:8px;
               border:1px solid var(--border);background:transparent;
               color:var(--text2);cursor:pointer;font-family:var(--font);
               font-size:12px;display:flex;align-items:center;justify-content:center;gap:6px">
        🗺️ Báo sai vị trí & cập nhật
      </button>`;
  }
}

function _findNearbyStores(lat, lon, maxMeters) {
  const results = [];
  (allFeatures || []).forEach(f => {
    if (!f.geometry?.coordinates) return;
    const [flon, flat] = f.geometry.coordinates;
    const dist = _haversineJs(lat, lon, flat, flon);
    if (dist <= maxMeters) {
      results.push({ name: f.properties.name, code: f.properties.code, dist: Math.round(dist) });
    }
  });
  return results.sort((a, b) => a.dist - b.dist);
}

function _haversineJs(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
    Math.cos(lat1 * Math.PI/180) * Math.cos(lat2 * Math.PI/180) * Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}