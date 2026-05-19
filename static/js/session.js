// session.js - Quan ly phien check-in/checkout

let activeSession = null;
let sessionTimer  = null;
let minMinutes    = 15;
let checkinActivityDays = 7;
let callActivityDays    = 7;

// ── Load session khi vao app ──────────────────────────────────
async function loadActiveSession() {
  try {
    const [res, settings, actRes] = await Promise.all([
      api.getActiveSession(),
      api.getSessionSettings(),
      fetch('/api/calls/activity-days', {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('sf_token')}` }
      }).then(r => r.json()).catch(() => ({})),
    ]);
    minMinutes          = settings.min_checkin_minutes;
    checkinActivityDays = actRes.checkin_activity_days || actRes.activity_days || 7;
    callActivityDays    = actRes.call_activity_days    || actRes.activity_days || 7;
    if (res.active) {
      activeSession = res;
      showResumeBanner(res);
    }
  } catch {}

}

// ── Banner thong bao session dang mo (thay cho auto-open) ─────
function showResumeBanner(sess) {
  // Xoa banner cu neu co
  document.getElementById('resume-banner')?.remove();

  const banner = document.createElement('div');
  banner.id = 'resume-banner';
  banner.style.cssText = `
    position:fixed;bottom:0;left:0;right:0;z-index:900;
    background:#b91c1c;color:#fff;
    padding:12px 16px;
    display:flex;align-items:center;gap:10px;
    font-family:var(--font);font-size:13px;
    box-shadow:0 -2px 12px rgba(0,0,0,.4);
  `;

  const elapsed = sess.elapsed_min || 0;
  banner.innerHTML = `
    <div style="flex:1;line-height:1.4">
      <div style="font-weight:600;font-size:14px">📍 Có phiên check-in chưa hoàn thành</div>
      <div style="opacity:.85;font-size:12px;margin-top:2px">${sess.store_name} · ${elapsed} phút trước</div>
    </div>
    <button onclick="resumeSession()" style="
      padding:8px 14px;background:#fff;color:#b91c1c;
      border:none;border-radius:8px;cursor:pointer;
      font-family:var(--font);font-size:13px;font-weight:600;
      white-space:nowrap;flex-shrink:0;
    ">Tiếp tục</button>
    <button onclick="cancelSessionFromBanner()" style="
      padding:8px 12px;background:rgba(255,255,255,.2);color:#fff;
      border:1px solid rgba(255,255,255,.4);border-radius:8px;cursor:pointer;
      font-family:var(--font);font-size:13px;
      white-space:nowrap;flex-shrink:0;
    ">Huỷ</button>
  `;
  document.body.appendChild(banner);
}

function resumeSession() {
  document.getElementById('resume-banner')?.remove();
  if (activeSession) showWorkingScreen(activeSession);
}

async function cancelSessionFromBanner() {
  if (!confirm('Huỷ phiên check-in đang dở? Dữ liệu sẽ mất.')) return;
  try {
    await fetch('/api/session/cancel', {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('sf_token')}`,
      },
      body: JSON.stringify({ session_id: activeSession.session_id }),
    });
    activeSession = null;
    document.getElementById('resume-banner')?.remove();
    showToast('Đã huỷ phiên check-in cũ', 'success');
    loadMapData();
  } catch(e) {
    showToast('Lỗi huỷ session: ' + e.message, 'error');
  }
}

// ── Bat dau check-in ─────────────────────────────────────────
async function startCheckin(storeId, storeName) {
  const gpsEl = document.getElementById('ci-gps-status');
  gpsEl.textContent = '📡 Đang lấy GPS...';
  gpsEl.className   = 'gps-status';

  navigator.geolocation.getCurrentPosition(async pos => {
    const { latitude: lat, longitude: lon, accuracy } = pos.coords;
    gpsEl.textContent = `✅ ${lat.toFixed(6)}, ${lon.toFixed(6)} (±${Math.round(accuracy)}m)`;
    gpsEl.className   = 'gps-status ok';

    try {
      const res = await fetch('/api/session/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('sf_token')}`,
        },
        body: JSON.stringify({ store_id: storeId, latitude: lat, longitude: lon }),
      }).then(r => r.json());

      if (res.error) { showToast(res.error, 'error'); return; }

      activeSession = {
        session_id: res.session_id,
        store_id:   storeId,
        store_name: storeName,
        checkin_at: res.checkin_at,
        elapsed_min: 0,
        photo1_url: null, photo2_url: null, photo3_url: null,
      };
      minMinutes = res.min_checkin_minutes;

      // Xoa banner cu neu co
      document.getElementById('resume-banner')?.remove();

      closeModal('modal-checkin-start');
      showWorkingScreen(activeSession);
      showToast(`Check-in thành công tại ${storeName}`, 'success');
      loadMapData();
    } catch(e) { showToast(e.message, 'error'); }
  }, err => {
    gpsEl.textContent = '❌ Không lấy được GPS';
    gpsEl.className   = 'gps-status err';
  }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
}

// ── Hien man hinh lam viec ───────────────────────────────────
function showWorkingScreen(sess) {
  activeSession = sess;

  // Dong tat ca modal dang mo
  document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
  // Dong bottom sheet
  document.getElementById('store-sheet')?.classList.add('hidden');
  // Dong banner neu con
  document.getElementById('resume-banner')?.remove();

  document.getElementById('working-store-name').textContent = sess.store_name;
  document.getElementById('working-screen').classList.remove('hidden');
  document.getElementById('fab-checkin').classList.add('hidden');

  // Update anh neu co
  updatePhotoSlot(1, sess.photo1_url);
  updatePhotoSlot(2, sess.photo2_url);
  // Slot 3: dung grid
  if (!sess.photo3_urls) {
    sess.photo3_urls = sess.photo3_url ? [sess.photo3_url] : [];
  }
  updatePhotoSlot3Grid();

  if (sess.note) document.getElementById('working-note').value = sess.note;

  startTimer();
}

function hideWorkingScreen() {
  document.getElementById('working-screen').classList.add('hidden');
  stopTimer();
}

// ── Timer ─────────────────────────────────────────────────────
function startTimer() {
  stopTimer();
  updateTimer();
  sessionTimer = setInterval(updateTimer, 10000); // update moi 10 giay
}

function stopTimer() {
  if (sessionTimer) { clearInterval(sessionTimer); sessionTimer = null; }
}

function updateTimer() {
  if (!activeSession?.checkin_at) return;
  const ci = new Date(activeSession.checkin_at);
  const elapsed = Math.floor((Date.now() - ci.getTime()) / 60000);
  const h = Math.floor(elapsed / 60);
  const m = elapsed % 60;
  const display = h > 0 ? `${h}g ${m}p` : `${m} phút`;
  document.getElementById('working-timer').textContent = display;

  // Hien thi tien trinh
  const pct = Math.min(100, (elapsed / minMinutes) * 100);
  document.getElementById('timer-progress').style.width = pct + '%';

  const btn = document.getElementById('btn-checkout');
  const hint = document.getElementById('checkout-hint');
  btn.disabled = false;
  if (elapsed >= minMinutes) {
    document.getElementById('timer-progress').style.background = 'var(--success)';
    document.getElementById('working-timer').style.color = 'var(--success)';
    btn.style.opacity = '1';
    btn.style.background = 'var(--success)';
    hint.textContent = '✅ Đủ thời gian, có thể check-out';
    hint.style.color = 'var(--success)';
  } else {
    const remaining = minMinutes - elapsed;
    btn.style.opacity = '0.7';
    btn.style.background = 'var(--warn)';
    hint.textContent = `⚠️ Còn ${remaining} phút (check-out sớm sẽ bị ghi chú)`;
    hint.style.color = 'var(--warn)';
  }
}

// ── Upload anh ───────────────────────────────────────────────
function triggerPhotoSlot(slot, subIndex = 0) {
  // Hien menu lua chon: chup anh hoac chon tu thu vien
  const existing = document.getElementById('photo-choice-menu');
  if (existing) existing.remove();

  const menu = document.createElement('div');
  menu.id = 'photo-choice-menu';
  menu.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,.5);
    z-index:9999;display:flex;align-items:flex-end;justify-content:center;
  `;
  menu.innerHTML = `
    <div style="background:var(--surface);border-radius:16px 16px 0 0;padding:16px;width:100%;max-width:480px;margin:0 auto">
      <div style="text-align:center;font-size:13px;color:var(--text2);margin-bottom:12px;font-weight:500">
        ${slot === 3 ? 'Ảnh đối thủ cạnh tranh' : slot === 2 ? 'Ảnh sản phẩm BRICON' : 'Ảnh bảng hiệu cửa hàng'}
      </div>
      <button onclick="pickPhoto(${slot}, ${subIndex}, 'camera')" style="
        display:flex;align-items:center;gap:12px;width:100%;padding:14px 16px;
        background:var(--surface2);border:none;border-radius:10px;margin-bottom:8px;
        color:var(--text);font-family:var(--font);font-size:15px;cursor:pointer;
      ">📷 <span>Chụp ảnh</span></button>
      <button onclick="pickPhoto(${slot}, ${subIndex}, 'gallery')" style="
        display:flex;align-items:center;gap:12px;width:100%;padding:14px 16px;
        background:var(--surface2);border:none;border-radius:10px;margin-bottom:8px;
        color:var(--text);font-family:var(--font);font-size:15px;cursor:pointer;
      ">🖼️ <span>Chọn từ thư viện</span></button>
      <button onclick="document.getElementById('photo-choice-menu').remove()" style="
        display:block;width:100%;padding:12px;margin-top:4px;
        background:transparent;border:1px solid var(--border);border-radius:10px;
        color:var(--text2);font-family:var(--font);font-size:14px;cursor:pointer;
      ">Huỷ</button>
    </div>
  `;
  menu.onclick = (e) => { if (e.target === menu) menu.remove(); };
  document.body.appendChild(menu);
}

function pickPhoto(slot, subIndex, mode) {
  document.getElementById('photo-choice-menu')?.remove();
  const inputId = slot === 3 ? `photo-input-3-${subIndex}` : `photo-input-${slot}`;
  let input = document.getElementById(inputId);
  if (!input) {
    input = document.createElement('input');
    input.type = 'file';
    input.id = inputId;
    input.accept = 'image/*';
    input.style.display = 'none';
    input.onchange = () => handlePhotoSlot(input, slot, subIndex);
    document.body.appendChild(input);
  }
  if (mode === 'camera') {
    input.setAttribute('capture', 'environment');
  } else {
    input.removeAttribute('capture');
  }
  input.value = '';
  input.click();
}

async function handlePhotoSlot(input, slot, subIndex = 0) {
  const file = input.files[0];
  if (!file || !activeSession) return;

  const elId = slot === 3 ? `photo-slot-3-${subIndex}` : `photo-slot-${slot}`;
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = '<div style="padding:12px;color:var(--text2);font-size:12px">📡 Đang lấy GPS...</div>';

  navigator.geolocation.getCurrentPosition(async pos => {
    const { latitude: lat, longitude: lon } = pos.coords;

    const fd = new FormData();
    fd.append('session_id', activeSession.session_id);
    fd.append('slot', slot);
    fd.append('latitude', lat);
    fd.append('longitude', lon);
    fd.append('photo', file);

    el.innerHTML = '<div style="padding:12px;color:var(--text2);font-size:12px">⏳ Đang upload...</div>';

    try {
      const res = await fetch('/api/session/photo', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('sf_token')}` },
        body: fd,
      }).then(r => r.json());

      if (res.error) {
        showToast(res.error, 'error');
        el.innerHTML = `<div onclick="triggerPhotoSlot(${slot}, ${subIndex})" class="photo-slot-empty">${photoSlotLabel(slot)}</div>`;
        return;
      }

      if (slot === 3) {
        // Luu vao mang anh doi thu
        if (!activeSession.photo3_urls) activeSession.photo3_urls = [];
        if (subIndex < activeSession.photo3_urls.length) {
          activeSession.photo3_urls[subIndex] = res.url;
        } else {
          activeSession.photo3_urls.push(res.url);
        }
        activeSession.photo3_url = activeSession.photo3_urls[0]; // backward compat
        updatePhotoSlot3Grid();
      } else {
        activeSession[`photo${slot}_url`] = res.url;
        updatePhotoSlot(slot, res.url);
      }
      showToast(`Ảnh đã lưu`, 'success');
    } catch(e) {
      showToast('Upload thất bại', 'error');
      el.innerHTML = `<div onclick="triggerPhotoSlot(${slot})" class="photo-slot-empty">${photoSlotLabel(slot)}</div>`;
    }
  }, () => {
    showToast('Không lấy được GPS', 'error');
    el.innerHTML = `<div onclick="triggerPhotoSlot(${slot})" class="photo-slot-empty">${photoSlotLabel(slot)}</div>`;
  }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
}

function photoSlotLabel(slot) {
  const labels = {
    1: '📷 Ảnh bảng hiệu <span style="color:var(--danger)">*</span>',
    2: '📷 Sản phẩm BRICON',
    3: '📷 Sản phẩm đối thủ <span style="color:var(--danger)">*</span>',
  };
  return `<div style="text-align:center;padding:16px 8px;font-size:12px;color:var(--text2)">${labels[slot]}<br><span style="font-size:10px;margin-top:4px;display:block">Bấm để chụp</span></div>`;
}

function updatePhotoSlot(slot, url) {
  const el = document.getElementById(`photo-slot-${slot}`);
  if (!el) return;
  if (url) {
    el.innerHTML = `<div style="position:relative;cursor:pointer" onclick="triggerPhotoSlot(${slot})">
      <img src="${url}" style="width:100%;height:90px;object-fit:cover;border-radius:6px;display:block">
      <div style="position:absolute;top:4px;right:4px;background:var(--success);color:#fff;border-radius:4px;padding:2px 6px;font-size:10px;font-weight:600">✓</div>
    </div>`;
  } else {
    el.innerHTML = `<div onclick="triggerPhotoSlot(${slot})" class="photo-slot-empty">${photoSlotLabel(slot)}</div>`;
  }
}

function updatePhotoSlot3Grid() {
  const container = document.getElementById('photo-slot-3-container');
  if (!container) return;
  const urls = activeSession.photo3_urls || (activeSession.photo3_url ? [activeSession.photo3_url] : []);
  const maxPhotos = 5;

  let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">';

  // Hien cac anh da chup
  urls.forEach((url, i) => {
    html += `<div id="photo-slot-3-${i}" style="position:relative;cursor:pointer" onclick="triggerPhotoSlot(3,${i})">
      <img src="${url}" style="width:100%;height:70px;object-fit:cover;border-radius:6px;display:block">
      <div style="position:absolute;top:3px;right:3px;background:var(--success);color:#fff;border-radius:4px;padding:1px 5px;font-size:9px;font-weight:600">✓</div>
    </div>`;
  });

  // Nut them anh moi (neu chua du 5)
  if (urls.length < maxPhotos) {
    const nextIdx = urls.length;
    html += `<div id="photo-slot-3-${nextIdx}" onclick="triggerPhotoSlot(3,${nextIdx})"
      style="border:1.5px dashed var(--border);border-radius:6px;height:70px;
             display:flex;align-items:center;justify-content:center;cursor:pointer;
             background:var(--surface2);font-size:20px;color:var(--text2)">
      ${nextIdx === 0 ? '📷' : '+'}
    </div>`;
  }

  html += '</div>';
  container.innerHTML = html;
}

// ── Luu ghi chu ──────────────────────────────────────────────
let _noteTimer = null;
function onNoteChange(val) {
  clearTimeout(_noteTimer);
  _noteTimer = setTimeout(async () => {
    if (!activeSession) return;
    await fetch('/api/session/note', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('sf_token')}`,
      },
      body: JSON.stringify({ session_id: activeSession.session_id, note: val }),
    });
  }, 1000);
}

// ── Check-out ────────────────────────────────────────────────
async function doCheckout() {
  // Kiem tra co checkout som khong
  const ci = new Date(activeSession.checkin_at);
  const elapsed = Math.floor((Date.now() - ci.getTime()) / 60000);
  if (elapsed < minMinutes) {
    const remaining = minMinutes - elapsed;
    const ok = confirm(`⚠️ Bạn mới ở ${elapsed} phút (tối thiểu ${minMinutes} phút).\n\nCheck-out sớm sẽ được ghi chú "[CHECK-OUT SỚM]" trong báo cáo để sếp biết.\n\nBạn có chắc muốn check-out không?`);
    if (!ok) return;
  }

  const btn = document.getElementById('btn-checkout');
  btn.disabled = true;
  btn.textContent = 'Đang xử lý...';

  navigator.geolocation.getCurrentPosition(async pos => {
    const { latitude: lat, longitude: lon } = pos.coords;
    try {
      const res = await fetch('/api/session/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('sf_token')}`,
        },
        body: JSON.stringify({
          session_id: activeSession.session_id,
          latitude: lat, longitude: lon,
        }),
      }).then(r => r.json());

      if (res.error) {
        showToast(res.error, 'error');
        btn.disabled = false;
        btn.textContent = '✅ Check-out';
        return;
      }

      activeSession = null;
      hideWorkingScreen();
      showToast(res.message, 'success');
      loadMapData();
    } catch(e) {
      showToast(e.message, 'error');
      btn.disabled = false;
      btn.textContent = '✅ Check-out';
    }
  }, () => {
    showToast('Không lấy được GPS để check-out', 'error');
    btn.disabled = false;
    btn.textContent = '✅ Check-out';
  }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
}

// ── Huy check-in ─────────────────────────────────────────────
async function cancelSession() {
  if (!confirm('Huỷ check-in? Dữ liệu sẽ mất.')) return;
  try {
    await fetch('/api/session/cancel', {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('sf_token')}`,
      },
      body: JSON.stringify({ session_id: activeSession.session_id }),
    });
    activeSession = null;
    hideWorkingScreen();
    showToast('Đã huỷ check-in', 'success');
    loadMapData();
  } catch(e) { showToast(e.message, 'error'); }
}