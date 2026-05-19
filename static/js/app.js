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
  if (window.innerWidth <= 768 && sidebarOpen) {
    sidebarOpen = false;
    document.getElementById('sidebar').classList.add('collapsed');
    const overlay = document.getElementById('sidebar-overlay');
    if (overlay) overlay.remove();
  }
});

function renderStoreList(features) {
  const el = document.getElementById('store-list');
  const filtered = features.filter(f => currentFilter === 'all' || f.properties.type === currentFilter);
  if (!filtered.length) {
    el.innerHTML = '<div style="padding:12px;color:var(--text2);font-size:12px;">Không có cửa hàng</div>';
    return;
  }
  el.innerHTML = filtered.slice(0, 50).map(f => {
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
  renderStoreList(filtered);
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
  const role = currentUser?.role || '';
  if (btnCI)   btnCI.style.display   = (role === 'telesales') ? 'none' : '';
  if (btnCall) btnCall.style.display = '';

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
  document.getElementById('new-store-gps').textContent = '📡 Chưa lấy GPS';
  document.getElementById('new-store-gps').className  = 'gps-status';
  document.getElementById('name-check-msg').textContent = '';
  newStoreGPS = null;
  _fetchAutoCode('new');
  document.getElementById('modal-add-store').classList.remove('hidden');
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
  const name = input.value.trim();
  const msg = document.getElementById('name-check-msg');
  if (!name) { msg.textContent = ''; return; }
  clearTimeout(_nameCheckTimer);
  _nameCheckTimer = setTimeout(async () => {
    try {
      const res = await api.checkStoreName(name);
      if (res.duplicate) {
        msg.textContent = `❌ Tên "${res.existing}" đã tồn tại`;
        msg.style.color = 'var(--danger)';
      } else {
        msg.textContent = '✅ Tên hợp lệ';
        msg.style.color = 'var(--success)';
      }
    } catch {}
  }, 500);
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

  try {
    const check = await api.checkStoreName(name);
    if (check.duplicate) { showToast(`Tên "${check.existing}" đã tồn tại`, 'error'); return; }
  } catch {}

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