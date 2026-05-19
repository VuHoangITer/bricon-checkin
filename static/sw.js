const CACHE = 'sf-v1';
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
    caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // API calls - network first
  if (e.request.url.includes('/api/')) {
    e.respondWith(
      fetch(e.request).catch(() => new Response('{"error":"Offline"}', {
        headers: { 'Content-Type': 'application/json' }
      }))
    );
    return;
  }
  // Static - cache first
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});