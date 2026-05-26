// Đổi tên cache để force SW update, xóa cache cũ
const CACHE = 'sf-v3';
const ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/api.js',
  '/static/js/map.js',
  '/static/js/app.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(ASSETS))
      .then(() => self.skipWaiting())  // activate ngay, không chờ tab cũ đóng
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())  // claim tất cả tab ngay lập tức
  );
});

self.addEventListener('fetch', e => {
  // API calls - luôn network first, không cache
  if (e.request.url.includes('/api/')) {
    e.respondWith(
      fetch(e.request).catch(() => new Response('{"error":"Offline"}', {
        headers: { 'Content-Type': 'application/json' }
      }))
    );
    return;
  }

  // HTML files (index, login) - network first để luôn lấy bản mới nhất
  if (e.request.headers.get('accept')?.includes('text/html')) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Static assets (JS, CSS) - network first để luôn lấy code mới
  if (e.request.url.includes('/static/js/') || e.request.url.includes('/static/css/')) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Còn lại - cache first
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});