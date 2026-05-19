const API = { AUTH: "/api/auth", STORE: "/api/stores", CHECKIN: "/api/checkin" };
let _token = localStorage.getItem("sf_token") || null;
function setToken(t)  { _token = t; localStorage.setItem("sf_token", t); }
function clearToken() { _token = null; localStorage.removeItem("sf_token"); localStorage.removeItem("sf_user"); }

async function req(method, url, body = null, isForm = false) {
  const headers = {};
  if (_token) headers["Authorization"] = `Bearer ${_token}`;
  if (!isForm && body) headers["Content-Type"] = "application/json";
  const res = await fetch(url, { method, headers, body: isForm ? body : (body ? JSON.stringify(body) : null) });
  if (res.status === 401) { clearToken(); showLogin(); throw new Error("Phiên đã hết hạn"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

const api = {
  login:  (u, p) => req("POST", `${API.AUTH}/login`, { username: u, password: p }),
  me:     ()     => req("GET",  `${API.AUTH}/me`),
  users:  ()     => req("GET",  `${API.AUTH}/users`),

  storesGeoJSON:  ()      => req("GET",  `${API.STORE}/geojson`),
  storesList:     (p={})  => req("GET",  `${API.STORE}/?${new URLSearchParams(p)}`),
  createStore:    (d)     => req("POST", `${API.STORE}/`, d),
  updateStore:    (id, d) => req("PUT",  `${API.STORE}/${id}`, d),

  // Kiem tra ten trung
  checkStoreName: (name)       => req("POST", `${API.STORE}/check-name`, { name }),
  // Lay ma tu dong
  autoCode:       (store_type) => req("POST", `${API.STORE}/auto-code`,  { store_type }),

  assign:  (user_id, store_id, note) => req("POST", `${API.STORE}/assignments`, { user_id, store_id, note }),
  checkin: (fd)   => req("POST", `${API.CHECKIN}/`,       fd, true),
  history: (p={}) => req("GET",  `${API.CHECKIN}/history?${new URLSearchParams(p)}`),

  // Session
  getActiveSession:   ()  => req("GET", "/api/session/active"),
  getSessionSettings: ()  => req("GET", "/api/session/settings"),
};